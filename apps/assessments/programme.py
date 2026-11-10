"""The final exam and the pre-test (architecture §11).

Both are drawn from the `final` pool. The pre-test is the blueprint's anchor questions only, once
(resumable). The final takes `per_module` questions from each module's final pool, always
including the anchors, and unlocks by the §10.2 rules. Questions are drawn the same way for every
learner so scores compare, and the anchors are never given feedback anywhere.
"""

import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import audit
from apps.questions import formats
from apps.questions.models import Pool, Question, QuestionStatus
from apps.results.policy import compute_results

from .models import (
    Attempt,
    AttemptItem,
    AttemptStatus,
    ProgrammeAssessment,
    ProgrammeAssessmentKind,
)
from .services import PartNotAvailable, _latest_versions

# Today's blueprint (architecture §11): 6/6/5/6/6/6/5/5/5 = 50 questions, anchors included.
DEFAULT_PER_MODULE = {1: 6, 2: 6, 3: 5, 4: 6, 5: 6, 6: 6, 7: 5, 8: 5, 9: 5}
SUBMITTED = (AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED)


class Locked(PartNotAvailable):
    """The final is not unlocked, or a cooldown is running. `reasons` says why in plain words."""

    def __init__(self, reasons):
        super().__init__(" ".join(reasons))
        self.reasons = reasons


class AlreadyDone(PartNotAvailable):
    pass


def get_assessment(kind: str) -> ProgrammeAssessment:
    assessment, _ = ProgrammeAssessment.objects.get_or_create(
        kind=kind,
        defaults={
            "blueprint": {
                "per_module": {str(k): v for k, v in DEFAULT_PER_MODULE.items()},
                "anchors": [],
            }
            if kind == ProgrammeAssessmentKind.FINAL
            else {"anchors": []},
            "time_display_minutes": 60 if kind == ProgrammeAssessmentKind.FINAL else None,
        },
    )
    return assessment


def anchor_ids(blueprint: dict | None = None) -> list[int]:
    """The anchor question ids: the blueprint's list, or every live final-pool anchor."""
    listed = (blueprint or {}).get("anchors")
    if listed:
        return list(listed)
    return list(
        Question.objects.filter(is_anchor=True, pool=Pool.FINAL, status=QuestionStatus.LIVE)
        .order_by("stable_id")
        .values_list("pk", flat=True)
    )


def pretest_available() -> bool:
    return bool(anchor_ids(get_assessment(ProgrammeAssessmentKind.PRETEST).blueprint))


def final_locked_reasons(user) -> list[str]:
    """Why the final cannot be started now; empty when it can (§10.2)."""
    result = compute_results([user.pk])[user.pk]
    reasons = []
    if not result.pretest_done:
        reasons.append(
            "Do the pre-test first."
            if pretest_available()
            else "The pre-test is not available yet."
        )
    for module in result.modules:
        for part in module.parts:
            if not part.answered:
                reasons.append(
                    f"Module {module.number}, {part.name}: submit it once with every question answered."
                )
    return reasons


def _cooldown_reason(user, assessment, now):
    if not assessment.cooldown_hours:
        return None
    last = (
        Attempt.objects.filter(user=user, programme_assessment=assessment, status__in=SUBMITTED)
        .order_by("-submitted_at")
        .first()
    )
    if (
        last
        and last.submitted_at
        and now < last.submitted_at + timedelta(hours=assessment.cooldown_hours)
    ):
        return f"Please wait {assessment.cooldown_hours} hours between final attempts."
    return None


def draw_programme(assessment, rng=None):
    rng = rng or random.SystemRandom()
    blueprint = assessment.blueprint or {}
    anchors = set(anchor_ids(blueprint))
    live = {v.question_id: v for v in _latest_versions(_final_pool())}
    if assessment.kind == ProgrammeAssessmentKind.PRETEST:
        chosen = [live[a] for a in sorted(anchors) if a in live]
        rng.shuffle(chosen)
        return chosen
    chosen = []
    for module_key, wanted in sorted(
        (blueprint.get("per_module") or {}).items(), key=lambda kv: int(kv[0])
    ):
        pool = [v for v in live.values() if v.question.module.number == int(module_key)]
        fixed = [v for v in pool if v.question_id in anchors]
        rest = [v for v in pool if v.question_id not in anchors]
        rng.shuffle(rest)
        need = wanted - len(fixed)
        if need < 0 or len(rest) < need:
            raise PartNotAvailable("The final exam is not ready yet.")
        chosen += fixed + rest[:need]
    rng.shuffle(chosen)
    return chosen


def _final_pool():
    return Question.objects.filter(pool=Pool.FINAL, status=QuestionStatus.LIVE).select_related(
        "module"
    )


@transaction.atomic
def start_programme(user, kind: str, rng=None, now=None) -> tuple[Attempt, bool]:
    """Start (or resume) the pre-test or the final. Returns (attempt, created)."""
    now = now or timezone.now()
    assessment = get_assessment(kind)
    User.objects.select_for_update().get(pk=user.pk)
    existing = Attempt.objects.filter(
        user=user, programme_assessment=assessment, status=AttemptStatus.IN_PROGRESS
    ).first()
    if existing:
        return existing, False
    if kind == ProgrammeAssessmentKind.PRETEST:
        if Attempt.objects.filter(
            user=user, programme_assessment=assessment, status__in=SUBMITTED
        ).exists():
            raise AlreadyDone("You have already done the pre-test.")
    elif kind == ProgrammeAssessmentKind.FINAL:
        reasons = final_locked_reasons(user)
        cooldown = _cooldown_reason(user, assessment, now)
        if cooldown:
            reasons.append(cooldown)
        if reasons:
            raise Locked(reasons)
    else:
        raise PartNotAvailable("That assessment is not available.")
    versions = draw_programme(assessment, rng)
    if not versions:
        raise PartNotAvailable("This assessment has no questions yet.")
    number = (
        Attempt.objects.filter(user=user, programme_assessment=assessment).aggregate(
            n=Max("number")
        )["n"]
        or 0
    ) + 1
    attempt = Attempt.objects.create(user=user, programme_assessment=assessment, number=number)
    AttemptItem.objects.bulk_create(
        AttemptItem(
            attempt=attempt, position=position, question_version=version,
            points=version.question.points, format=version.question.format,
            option_map=formats.make_map(version.question.format, version.body, rng),
        )
        for position, version in enumerate(versions, start=1)
    )  # fmt: skip
    audit("attempt.started", actor=user, target=attempt, assessment=assessment.pk, kind=kind, number=number, questions=len(versions))  # fmt: skip
    return attempt, True
