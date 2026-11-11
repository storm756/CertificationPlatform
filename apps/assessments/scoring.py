"""Server-side scorers, one per format (architecture §9.6). The browser never scores anything."""

from decimal import Decimal

ZERO = Decimal("0")
ONE = Decimal("1")


def score_mcq(body: dict, option_map: dict, response: dict | None) -> tuple[Decimal, bool]:
    """Right or wrong (1 or 0), and whether the chosen option is a safety-gate option (D25).

    The learner's response is a one-off token. It is mapped back to the internal option id here,
    on the server. Unanswered or an unknown token scores 0 and never raises the gate.
    """
    token = (response or {}).get("choice")
    key = option_map["tokens"].get(token) if token else None
    if key is None:
        return ZERO, False
    gate = key in body.get("gate", {})
    return (ONE if key == body["correct"] else ZERO), gate


SCORERS = {"mcq": score_mcq}
