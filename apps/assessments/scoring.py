"""Server-side scorers (architecture §9.6). The browser never scores anything.

The per-format rules live in apps/questions/formats.py, next to the token maps and projections.
"""

from decimal import Decimal

from apps.questions import formats


def score_item(
    fmt: str, body: dict, option_map: dict, response: dict | None
) -> tuple[Decimal, bool]:
    """(score from 0 to 1, whether a safety-gate choice was made) for one attempt item."""
    return formats.score(fmt, body, option_map, response)


def score_mcq(body: dict, option_map: dict, response: dict | None) -> tuple[Decimal, bool]:
    return formats.score("mcq", body, option_map, response)


SCORERS = {name: (lambda b, m, r, _n=name: formats.score(_n, b, m, r)) for name in formats.FORMATS}
