"""Learn-mode practice checks: POST /learn/check (architecture §8.4).

Only a live `practice`-pool question that a published unit uses in a `check` block is accepted.
Module-quiz and final questions are refused, so this endpoint can never reveal an assessment key.
The page gets the question with random one-off option tokens (kept in the session); after the
learner answers, the server scores it and returns the full answer: practice explains itself (D13).
"""

from decimal import Decimal

from django.utils.translation import gettext as _

from apps.questions import formats
from apps.questions.models import Pool, Question, QuestionStatus

from .models import LearnCheck, UnitType, UnitVersion, VersionStatus
from .services import complete

SUPPORTED = {"mcq"}


class CheckRefused(Exception):
    pass


def _session_key(version_id):
    return f"learncheck:{version_id}"


def practice_question(stable_id: str):
    """The live practice question with this id, or None (quiz and final questions are None)."""
    return Question.objects.filter(
        stable_id=stable_id,
        pool=Pool.PRACTICE,
        status=QuestionStatus.LIVE,
        format__in=SUPPORTED,
    ).first()


def used_by_published_unit(unit, stable_id: str) -> bool:
    version = UnitVersion.objects.filter(unit=unit, status=VersionStatus.PUBLISHED).first()
    return bool(version) and any(
        b.get("type") == "check" and b.get("question") == stable_id for b in version.blocks
    )


def prepare(session, stable_id: str):
    """What the page shows for a check block: the stem and options as fresh tokens. No key."""
    question = practice_question(stable_id)
    if question is None:
        return None
    version = question.current_version
    option_map = formats.make_map(question.format, version.body)
    session[_session_key(version.pk)] = option_map
    return {
        "stable_id": question.stable_id,
        "q": formats.project(question.format, version.body, option_map),
    }


def answer(user, unit, stable_id: str, choice: str, session) -> dict:
    """Score a practice answer and return the full explanation."""
    question = practice_question(stable_id)
    if question is None or not used_by_published_unit(unit, stable_id):
        raise CheckRefused(_("This question is not a practice check."))
    version = question.current_version
    option_map = session.get(_session_key(version.pk))
    if not option_map:
        raise CheckRefused(_("Reload the page and try again."))
    try:
        response = formats.clean_response(
            question.format, version.body, option_map, {"choice": choice}
        )
    except formats.ResponseError as exc:
        raise CheckRefused(str(exc)) from None
    score, _gate = formats.score(question.format, version.body, option_map, response)
    if user is not None:  # a signed-out visitor gets feedback but leaves no record
        LearnCheck.objects.create(user=user, question_version=version, unit=unit, score=score)
        if unit.type == UnitType.CHECK:
            complete(user, unit, how="attempted")
    body = version.body
    right_text = next(o["text"] for o in body["options"] if o["id"] == body["correct"])
    return {
        "right": score == Decimal(1),
        "right_text": right_text,  # practice only: the full answer (§8.4, D13)
        "hint": body.get("hint", ""),
        "stable_id": stable_id,
    }
