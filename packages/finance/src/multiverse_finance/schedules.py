"""Time-lag schedules: when an effect arrives, in quarters counted from 1.

A schedule is a tuple with one value per quarter of the horizon: index 0 is quarter 1. What
falls after the horizon is not in the tuple, so a sum over a schedule can be smaller than the
amount it spreads.
"""

from collections.abc import Sequence
from decimal import Decimal

from multiverse_finance.exact import ONE, ZERO, whole


def ramp(horizon: int, start: int, quarters: int) -> tuple[Decimal, ...]:
    """Share of the full effect in each quarter: 0 before ``start``, then a straight line.

    Over ``quarters`` quarters the share climbs to 1, so 2 gives 1/2 at ``start`` and 1 a
    quarter later. 0 and 1 both give the full effect at once.
    """
    whole(start, 1, "ramp.start")
    whole(quarters, 0, "ramp.quarters")
    steps = Decimal(max(quarters, 1))
    return tuple(
        ZERO if quarter < start else min(ONE, Decimal(quarter - start + 1) / steps)
        for quarter in range(1, horizon + 1)
    )


def shifted(series: Sequence[Decimal], quarters: int) -> tuple[Decimal, ...]:
    """The same series ``quarters`` later, on the same horizon."""
    whole(quarters, 0, "shifted.quarters")
    kept = len(series) - min(quarters, len(series))
    return (ZERO,) * (len(series) - kept) + tuple(series[:kept])


def spread(amount: Decimal, start: int, quarters: int, horizon: int) -> tuple[Decimal, ...]:
    """Equal parts of ``amount`` over ``quarters`` quarters from ``start``; 0 means all at once."""
    whole(start, 1, "spread.start")
    whole(quarters, 0, "spread.quarters")
    parts = max(quarters, 1)
    return tuple(
        amount / parts if start <= quarter < start + parts else ZERO
        for quarter in range(1, horizon + 1)
    )
