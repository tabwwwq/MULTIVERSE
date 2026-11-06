"""Stress cases of docs/07 as changes of the baseline: the engine then books them like any path.

Delayed synergies and a failed deal are terms of the decision (``synergy_delay_quarters``,
``completed``). An FX crisis needs a second currency, which V1 to V3 refuse (D-04).
"""

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal

from multiverse_finance.exact import ONE, exact, finite, share, whole
from multiverse_finance.model import Baseline, Drivers


def _from_quarter(baseline: Baseline, start: int, change: Callable[[Drivers], Drivers]) -> Baseline:
    whole(start, 1, "stress.start")
    return replace(
        baseline,
        quarters=tuple(
            change(drivers) if quarter >= start else drivers
            for quarter, drivers in enumerate(baseline.quarters, 1)
        ),
    )


@exact
def revenue_shock(baseline: Baseline, fall: Decimal, start: int = 1) -> Baseline:
    """Revenue of every segment falls by ``fall`` from ``start`` on: 0.2 is the −20% case."""
    kept = ONE - share(fall, "stress.fall")
    return _from_quarter(
        baseline,
        start,
        lambda d: replace(d, segments=tuple((name, value * kept) for name, value in d.segments)),
    )


@exact
def margin_compression(baseline: Baseline, points: Decimal, start: int = 1) -> Baseline:
    """COGS rises by ``points`` of revenue: 0.03 takes three points off the gross margin."""
    share(points, "stress.points")
    return _from_quarter(baseline, start, lambda d: replace(d, cogs_ratio=d.cogs_ratio + points))


@exact
def working_capital_absorption(baseline: Baseline, points: Decimal, start: int = 1) -> Baseline:
    """Trade NWC takes ``points`` more of annualized revenue."""
    share(points, "stress.points")
    return _from_quarter(baseline, start, lambda d: replace(d, nwc_ratio=d.nwc_ratio + points))


@exact
def rate_shock(baseline: Baseline, points: Decimal) -> Baseline:
    """Floating debt, the revolver and new debt reprice at once: 0.02 is the +200 bps case."""
    finite(points, "stress.points")
    policy = baseline.policy
    tranches = tuple(
        replace(tranche, annual_rate=tranche.annual_rate + points) if tranche.floating else tranche
        for tranche in baseline.opening.tranches
    )
    return replace(
        baseline,
        opening=replace(baseline.opening, tranches=tranches),
        policy=replace(
            policy,
            revolver_rate=policy.revolver_rate + points,
            marginal_debt_rate=policy.marginal_debt_rate + points,
        ),
    )


def maturity_wall(baseline: Baseline, quarter: int) -> Baseline:
    """Term debt with no known maturity falls due in ``quarter``: an assumption made to test it."""
    whole(quarter, 1, "stress.quarter")
    tranches = tuple(
        tranche if tranche.maturity_quarter else replace(tranche, maturity_quarter=quarter)
        for tranche in baseline.opening.tranches
    )
    return replace(baseline, opening=replace(baseline.opening, tranches=tranches))


def refinancing_closed(baseline: Baseline) -> Baseline:
    """Lenders roll nothing: every maturity must be paid from cash or the revolver."""
    return replace(baseline, policy=replace(baseline.policy, can_refinance=False))


def covenant(baseline: Baseline, max_leverage: Decimal) -> Baseline:
    """The same path against a tighter leverage limit."""
    return replace(baseline, policy=replace(baseline.policy, max_leverage=max_leverage))
