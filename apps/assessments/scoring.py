"""Server-side scorers (architecture §9.6). The browser never scores anything.

The per-format rules live in apps/questions/formats.py, next to the token maps and projections.
"""

from decimal import Decimal

from apps.questions import formats


def untouched(response) -> bool:
    """True when the learner gave nothing: no response, or only the "mark for review" flag, or
    empty lists and objects with no "I'm finished" tick. A deliberate "none of these" (finished
    ticked) or any placed, picked or typed value is an answer."""
    if not isinstance(response, dict):
        return True
    return not any(value for key, value in response.items() if key != "flag")


def score_item(
    fmt: str, body: dict, option_map: dict, response: dict | None
) -> tuple[Decimal, bool]:
    """(score from 0 to 1, whether a safety-gate choice was made) for one attempt item.

    An item the learner never touched earns zero and cannot gate. The format scorers follow the
    legacy engine, which gives untouched "tick the right ones" and settings rows some credit for
    leaving things alone; that only makes sense once the learner has pressed Check, so it is
    never applied to a blank item at submission (manual or automatic).
    """
    if untouched(response):
        return Decimal("0"), False
    return formats.score(fmt, body, option_map, response)


def score_mcq(body: dict, option_map: dict, response: dict | None) -> tuple[Decimal, bool]:
    return formats.score("mcq", body, option_map, response)


SCORERS = {name: (lambda b, m, r, _n=name: formats.score(_n, b, m, r)) for name in formats.FORMATS}
