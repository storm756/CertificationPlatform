"""The one place scores are rounded and the pass mark lives (CLAUDE.md: Decimals, never floats)."""

from decimal import ROUND_HALF_UP, Decimal

PASS_MARK = Decimal("50")  # module and final pass mark, D2
HUNDRED = Decimal("100")
ONE_DECIMAL = Decimal("0.1")


def round1(value: Decimal) -> Decimal:
    """Round to one decimal place, halves up. The only rounding function for scores."""
    return Decimal(value).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)


def percent(earned: Decimal, total: Decimal) -> Decimal:
    """100 × earned / total, rounded once with round1. Zero when there is nothing to score."""
    if not total:
        return Decimal("0.0")
    return round1(HUNDRED * Decimal(earned) / Decimal(total))
