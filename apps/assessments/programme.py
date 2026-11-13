"""The final exam and the pre-test (architecture §11), served from the learner's exam set.

Each batch is assigned one released exam set (apps/assessments/examsets.py). The pre-test is that
set's shared baseline questions (two per module), once and resumable; the final is all of the
set's questions, including those same shared ones, and unlocks by the §10.2 rules. The set and the
question versions are frozen when the learner's first programme exam starts, and questions are
shuffled within the set, never mixed with another set. The shared questions get no feedback.
"""

import random
from datetime import timedelta

from django.db import transaction
from django.utils.translation import gettext as _
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import audit
from apps.questions import formats
from apps.results.policy import compute_results

from .models import (
    Attempt,
    AttemptItem,
    AttemptStatus,
    ProgrammeAssessment,
    ProgrammeAssessmentKind,
)
from .services import PartNotAvailable, check_attempt_limit

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
    assessment, _created = ProgrammeAssessment.objects.get_or_create(
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


def raw_blueprint():
    """The final's per-module counts exactly as stored (read-only: never creates the row)."""
    final = ProgrammeAssessment.objects.filter(kind=ProgrammeAssessmentKind.FINAL).first()
    per_module = ((final.blueprint if final else None) or {}).get("per_module")
    return per_module or {str(k): v for k, v in DEFAULT_PER_MODULE.items()}


def final_blueprint() -> dict[int, int]:
    """Questions per module in the final (the handoff blueprint, editable on the final's
    ProgrammeAssessment row by an admin). Unreadable entries are left out;
    examsets.blueprint_problems() reports them."""
    out = {}
    raw = raw_blueprint()
    for key, value in raw.items() if isinstance(raw, dict) else []:
        try:
            if isinstance(value, bool) or int(value) != value:
                continue
            out[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def pretest_available(user) -> bool:
    """The learner's batch (or their frozen choice) has a released exam set."""
    from . import examsets

    return examsets.assigned_set(user) is not None


def final_locked_reasons(user) -> list[str]:
    """Why the final cannot be started now; empty when it can (§10.2)."""
    result = compute_results([user.pk])[user.pk]
    reasons = []
    if result.setup_gaps:
        reasons.append(
            _("Course setup is incomplete, so the final cannot open yet.")
            + " "
            + " ".join(result.setup_gaps)
        )
    if not result.pretest_done:
        from . import examsets

        reasons.append(
            _("Do the pre-test first.")
            if pretest_available(user)
            else " ".join(
                [_("The pre-test is not available yet."), examsets.unavailable_reason(user) or ""]
            ).strip()
        )
    for module in result.modules:
        for part in module.parts:
            if not part.answered:
                reasons.append(
                    _("Module %(number)s, %(part)s: submit it once with every question answered.")
                    % {"number": module.number, "part": part.name}
                )
    return reasons


def cooldown_until(user, now=None):
    """When the learner may start the final again, if a configured cooldown is still running.
    Read-only: it never creates the settings row."""
    final = ProgrammeAssessment.objects.filter(kind=ProgrammeAssessmentKind.FINAL).first()
    if not final or not final.cooldown_hours:
        return None
    last = (
        Attempt.objects.filter(user=user, programme_assessment=final, status__in=SUBMITTED)
        .order_by("-submitted_at")
        .first()
    )
    if not last or not last.submitted_at:
        return None
    until = last.submitted_at + timedelta(hours=final.cooldown_hours)
    return until if (now or timezone.now()) < until else None


def _cooldown_reason(user, assessment, now):
    if not assessment.cooldown_hours:
        return None
    if cooldown_until(user, now):
        return _("Please wait %(hours)s hours between final attempts.") % {
            "hours": assessment.cooldown_hours
        }
    return None


def draw_programme(choice, kind, rng=None):
    """The frozen question versions for this exam, shuffled within the learner's set."""
    from apps.questions.models import QuestionVersion

    rng = rng or random.SystemRandom()
    wanted = (
        set(choice.pretest_question_ids)
        if kind == ProgrammeAssessmentKind.PRETEST
        else {int(q) for q in choice.versions}
    )
    ids = [v for q, v in choice.versions.items() if int(q) in wanted]
    chosen = list(QuestionVersion.objects.filter(pk__in=ids).select_related("question__module"))
    if len(chosen) != len(wanted):
        raise PartNotAvailable(_("This exam is not ready yet."))
    rng.shuffle(chosen)
    return chosen


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
            raise AlreadyDone(_("You have already done the pre-test."))
    elif kind == ProgrammeAssessmentKind.FINAL:
        reasons = final_locked_reasons(user)
        cooldown = _cooldown_reason(user, assessment, now)
        if cooldown:
            reasons.append(cooldown)
        if reasons:
            raise Locked(reasons)
        check_attempt_limit(
            assessment.max_attempts,
            Attempt.objects.filter(user=user, programme_assessment=assessment).count(),
        )
    else:
        raise PartNotAvailable(_("That assessment is not available."))
    from . import examsets

    try:
        choice = examsets.freeze(user)
    except LookupError as exc:
        raise PartNotAvailable(str(exc)) from None
    versions = draw_programme(choice, kind, rng)
    if not versions:
        raise PartNotAvailable(_("This assessment has no questions yet."))
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
    audit("attempt.started", actor=user, target=attempt, assessment=assessment.pk, kind=kind, number=number, questions=len(versions), exam_set=choice.exam_set.code)  # fmt: skip
    return attempt, True
