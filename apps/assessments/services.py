"""The attempt lifecycle: start (or resume), save an answer, submit, auto-submit (architecture §9).

Business rules live here, not in views or templates. Every function that changes an attempt runs
in a transaction and takes row locks in one order (user, then attempt) so two requests for the same
learner can never create two attempts or score one attempt twice.
"""

import logging
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import audit
from apps.questions import formats
from apps.questions.models import QuestionVersion
from apps.results.policy import percent

from .models import Attempt, AttemptItem, AttemptStatus
from .rules import live_questions
from .scoring import score_item

logger = logging.getLogger(__name__)


class AttemptError(Exception):
    """Base class: the view turns these into a message or an HTTP status."""


class PartNotAvailable(AttemptError):
    pass


class AttemptClosed(AttemptError):
    pass


class AttemptLimitReached(PartNotAvailable):
    """The learner has used every attempt the admin allowed (D32). Their best counted one counts."""


def attempt_allowance(limit: int | None, used: int) -> dict:
    """What the learner may still do under an optional attempt limit (D32).

    Every started attempt counts as used, whatever its status. Blank (None) is unlimited.
    """
    return {
        "limit": limit,
        "used": used,
        "left": None if limit is None else max(limit - used, 0),
        "reached": limit is not None and used >= limit,
    }


def check_attempt_limit(limit: int | None, used: int) -> None:
    """Called while the learner's row is locked, after an open attempt has been resumed, so two
    starts at the limit create at most one attempt and an attempt in progress is never cut off."""
    if attempt_allowance(limit, used)["reached"]:
        raise AttemptLimitReached(
            f"You have used all {limit} attempts allowed. Your best counted attempt still counts."
        )


def stored_max_attempts(obj) -> int | None:
    """The attempt limit as saved now (None for a new row), read before a change is saved."""
    if obj.pk is None:
        return None
    return type(obj).objects.filter(pk=obj.pk).values_list("max_attempts", flat=True).first()


def audit_limit_change(obj, old: int | None, *, actor=None, request=None) -> bool:
    """Audit a changed attempt limit on a part or the final (D32). Returns True if it changed."""
    if old == obj.max_attempts:
        return False
    audit(
        "assessment.max_attempts_changed",
        actor=actor,
        target=obj,
        request=request,
        old=old,
        new=obj.max_attempts,
    )
    return True


class InvalidAnswer(AttemptError):
    pass


# --- drawing -----------------------------------------------------------------------------------


def _latest_versions(questions) -> list[QuestionVersion]:
    """The current version of each question (Postgres DISTINCT ON), in stable_id order."""
    return list(
        QuestionVersion.objects.filter(question__in=questions)
        .order_by("question__stable_id", "-version")
        .distinct("question__stable_id")
        .select_related("question")
    )


def _previous_question_ids(user, part) -> set[int]:
    last = Attempt.objects.filter(user=user, part=part).order_by("-number").first()
    if not last:
        return set()
    return set(last.items.values_list("question_version__question_id", flat=True))


def draw(part, user, rng=None) -> list[QuestionVersion]:
    """Pick the questions for a new attempt (§9.1).

    `all` keeps the pool's order, `all_shuffled` shuffles it, `draw` takes `draw_n` at random with
    at least `min_per_tag` from every PC tag, avoiding the questions of this learner's previous
    attempt where the pool allows.
    """
    rng = rng or random.SystemRandom()
    versions = _latest_versions(live_questions(part))
    if part.selection == "all":
        return versions
    if part.selection == "all_shuffled":
        rng.shuffle(versions)
        return versions

    avoid = _previous_question_ids(user, part)
    fresh = [v for v in versions if v.question_id not in avoid]
    seen = [v for v in versions if v.question_id in avoid]
    rng.shuffle(fresh)
    rng.shuffle(seen)
    ordered = fresh + seen  # fresh questions are preferred everywhere below

    picked: list[QuestionVersion] = []
    if part.min_per_tag:
        by_tag: dict[str, list[QuestionVersion]] = {}
        for v in ordered:
            by_tag.setdefault(v.question.tags.get("pc") or "", []).append(v)
        for tag, group in sorted(by_tag.items()):
            if tag:
                picked.extend(group[: part.min_per_tag])
    chosen_ids = {v.pk for v in picked}
    picked.extend(v for v in ordered if v.pk not in chosen_ids)
    picked = picked[: part.draw_n]
    rng.shuffle(picked)
    return picked


def make_option_map(body: dict, rng=None) -> dict:
    """MCQ's option map: shuffled options with random one-off tokens (see formats.make_map)."""
    return formats.make_option_map(body, rng)


# --- start / resume ----------------------------------------------------------------------------


@transaction.atomic
def start(user, part, rng=None) -> tuple[Attempt, bool]:
    """Start a new attempt, or resume the one in progress. Returns (attempt, created).

    The learner's row is locked first, so two simultaneous starts run one after the other: the
    second finds the first's attempt and resumes it. The partial unique index is the backstop.
    """
    if not part.is_published:
        raise PartNotAvailable("This assessment is not available yet.")
    User.objects.select_for_update().get(pk=user.pk)
    existing = Attempt.objects.filter(
        user=user, part=part, status=AttemptStatus.IN_PROGRESS
    ).first()
    if existing:
        return existing, False
    check_attempt_limit(part.max_attempts, Attempt.objects.filter(user=user, part=part).count())

    versions = draw(part, user, rng)
    if not versions:
        raise PartNotAvailable("This assessment has no questions yet.")
    number = (Attempt.objects.filter(user=user, part=part).aggregate(n=Max("number"))["n"] or 0) + 1
    attempt = Attempt.objects.create(user=user, part=part, number=number)
    AttemptItem.objects.bulk_create(
        AttemptItem(
            attempt=attempt,
            position=position,
            question_version=version,  # frozen: edits make new versions, never change this one
            points=version.question.points,  # frozen
            format=version.question.format,
            option_map=formats.make_map(version.question.format, version.body, rng),
        )
        for position, version in enumerate(versions, start=1)
    )
    audit(
        "attempt.started",
        actor=user,
        target=attempt,
        part=part.pk,
        number=number,
        questions=len(versions),
    )
    return attempt, True


# --- answers -----------------------------------------------------------------------------------


@transaction.atomic
def save_answer(
    attempt_id, user, position, *, choice=None, flag=None, response=None, now=None
) -> AttemptItem:
    """Save the learner's answer and/or the "mark for review" flag. Returns no score.

    `choice` is MCQ's token. `response` is an interactive format's whole answer (tokens only); it
    replaces the saved one after the format checks that every token belongs to this item (§9.3).
    """
    attempt = Attempt.objects.select_for_update().get(pk=attempt_id, user=user)
    if not attempt.is_open:
        raise AttemptClosed("This attempt has already been submitted.")
    try:
        item = (
            attempt.items.select_for_update()
            .select_related("question_version")
            .get(position=position)
        )
    except AttemptItem.DoesNotExist:
        raise InvalidAnswer("No such question.") from None
    saved = dict(item.response or {})
    body = item.question_version.body
    try:
        if choice is not None:
            response = {"choice": choice}
        if response is not None:
            cleaned = formats.clean_response(item.format, body, item.option_map, response)
            saved = {**cleaned, **({"flag": saved["flag"]} if "flag" in saved else {})}
    except formats.ResponseError as exc:
        raise InvalidAnswer(str(exc)) from None
    if flag is not None:
        saved["flag"] = bool(flag)
    item.response = saved
    item.save(update_fields=["response"])
    attempt.last_saved_at = now or timezone.now()
    attempt.save(update_fields=["last_saved_at", "updated_at"])
    return item


# --- submit ------------------------------------------------------------------------------------


@transaction.atomic
def submit(attempt_id, user_id, *, auto=False, now=None, stale_before=None) -> Attempt:
    """Score an attempt with its frozen question versions. Safe to call twice (§9.4).

    Locks the user, then the attempt. A second call finds a closed attempt and returns it
    unchanged, so a double tap on Submit gives one result.

    `stale_before` is for the automatic job: once the attempt is locked, the last save is checked
    again, and an attempt saved since the job looked is left open for the learner.

    The returned attempt carries `just_closed`: True only when *this* call moved it from in
    progress to closed, decided while the lock is held (a retry, a manual submit that won the
    race, or another worker's auto-submit all give False).
    """
    User.objects.select_for_update().get(pk=user_id)
    attempt = Attempt.objects.select_for_update().get(pk=attempt_id, user_id=user_id)
    attempt.just_closed = False
    if not attempt.is_open:
        return attempt
    if stale_before is not None and attempt.last_saved_at >= stale_before:
        return attempt

    items = list(attempt.items.select_related("question_version"))
    earned = Decimal("0")
    total = Decimal("0")
    gate = False
    for item in items:
        version = item.question_version
        score, flagged = score_item(item.format, version.body, item.option_map, item.response)
        item.score, item.gate_flag = score, flagged
        earned += score * item.points
        total += item.points
        gate = gate or flagged
    AttemptItem.objects.bulk_update(items, ["score", "gate_flag"])

    attempt.score = percent(earned, total)
    attempt.all_answered = all(item.answered for item in items)
    attempt.gate_breached = gate
    attempt.counted = not gate  # submitted AND not gate_breached
    attempt.status = AttemptStatus.AUTO_SUBMITTED if auto else AttemptStatus.SUBMITTED
    attempt.submitted_at = now or timezone.now()
    attempt.save()
    audit(
        "attempt.auto_submitted" if auto else "attempt.submitted",
        actor=None if auto else attempt.user,
        target=attempt,
        part=attempt.part_id,
        number=attempt.number,
        all_answered=attempt.all_answered,
        gate_breached=gate,
    )
    attempt.just_closed = True
    return attempt


def auto_submit_stale(now=None) -> int:
    """Submit attempts with no save for STALE_ATTEMPT_DAYS, using their saved answers (§9.3).

    One attempt failing is logged and never stops the others. Returns how many were submitted.
    """
    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.STALE_ATTEMPT_DAYS)
    stale = list(
        Attempt.objects.filter(
            status=AttemptStatus.IN_PROGRESS, last_saved_at__lt=cutoff
        ).values_list("pk", "user_id")
    )
    done = 0
    for attempt_id, user_id in stale:
        try:
            submitted = submit(attempt_id, user_id, auto=True, now=now, stale_before=cutoff)
            done += 1 if getattr(submitted, "just_closed", False) else 0
        except Exception:
            logger.exception("auto-submit of attempt %s failed", attempt_id)
    if done:
        audit("system.auto_submit_stale", count=done)
    return done
