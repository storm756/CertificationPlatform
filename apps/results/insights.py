"""Derived views of attempts: the final's bands, knowledge gain, and a learner's weakest PCs."""

from collections import defaultdict
from decimal import Decimal

from .policy import ZERO, band, percent, round1

SUBMITTED = ("submitted", "auto_submitted")


def final_bands(attempt) -> list[dict]:
    """Per-module bands for one final attempt (§9.5): strong ≥ 75, OK 50–74.9, needs work < 50.

    Computed from that module's items in the attempt. The exact module % is never returned, so a
    learner cannot learn individual answers from small changes between attempts.
    """
    earned, total = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for item in attempt.items.select_related("question_version__question__module"):
        number = item.question_version.question.module.number
        earned[number] += (item.score or ZERO) * item.points
        total[number] += item.points
    return [{"module": n, "band": band(percent(earned[n], total[n]))} for n in sorted(total)]


def shared_percent(attempt, question_ids) -> Decimal | None:
    """The score of an attempt on these questions only, or None if it had none of them."""
    earned = total = ZERO
    for item in attempt.items.select_related("question_version"):
        if item.question_version.question_id in question_ids:
            earned += (item.score or ZERO) * item.points
            total += item.points
    return percent(earned, total) if total else None


def knowledge_gain(user) -> Decimal | None:
    """The shared pre-test questions: their score in the learner's FIRST final minus their score
    in the pre-test (CSR ≥ 25%). Both come from the learner's frozen exam set, so they are the same
    questions. None until both exist. Reported per batch by staff, never as learner feedback."""
    from apps.assessments.models import Attempt, LearnerExamSet, ProgrammeAssessmentKind

    choice = LearnerExamSet.objects.filter(user=user).first()
    if choice is None:
        return None
    shared = set(choice.pretest_question_ids)
    base = Attempt.objects.filter(user=user, status__in=SUBMITTED)
    pretest = base.filter(programme_assessment__kind=ProgrammeAssessmentKind.PRETEST).first()
    first_final = (
        base.filter(programme_assessment__kind=ProgrammeAssessmentKind.FINAL)
        .order_by("number")
        .first()
    )
    if not pretest or not first_final:
        return None
    before, after = shared_percent(pretest, shared), shared_percent(first_final, shared)
    if before is None or after is None:
        return None
    return round1(after - before)


def weakest_pcs(user, limit=3, minimum=2) -> list[dict]:
    """The learner's lowest PC tags from their counted multiple-choice part attempts."""
    from apps.assessments.models import AttemptItem

    earned, total = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    items = AttemptItem.objects.filter(
        attempt__user=user, attempt__status__in=SUBMITTED, attempt__counted=True,
        attempt__part__isnull=False, format="mcq",
    ).select_related("question_version__question")  # fmt: skip
    seen = defaultdict(int)
    for item in items:
        pc = item.question_version.question.tags.get("pc")
        if not pc:
            continue
        earned[pc] += (item.score or ZERO) * item.points
        total[pc] += item.points
        seen[pc] += 1
    rows = [
        {"pc": pc, "percent": percent(earned[pc], total[pc]), "items": seen[pc]}
        for pc in total
        if seen[pc] >= minimum
    ]
    return sorted(rows, key=lambda r: (r["percent"], r["pc"]))[:limit]
