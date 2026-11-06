"""Can a design identify anything here? Measured without reading a single treated outcome.

Every function takes the event quarter of treated firms and uses their data before it only:

- support and balance from covariates at the last quarter before the event;
- pre-trends from outcomes before the event, against matched controls;
- placebo dates inside the pre-period;
- a null distribution from pseudo-events on firms without the action, which also gives the
  smallest effect the sample could detect;
- a synthetic control fitted and checked on the pre-period.

A mean is a difference of differences across events; intervals use the spread between events.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from multiverse_causal.panel import COVARIATES, OUTCOMES, Floats, Panel
from multiverse_contracts.causal import (
    BalanceRow,
    LeadRow,
    NullRow,
    PlaceboRow,
    SyntheticFit,
)

PRE_QUARTERS = 8
LEADS = (-8, -7, -6, -5, -4, -3, -2)
SHIFTS = (6, 8, 10)
WINDOW = 4
DRAWS = 500
Z = 1.96
POWER_FACTOR = 2.8
MIN_DONORS = 20
FIT_QUARTERS = 8
HOLDOUT_QUARTERS = 4
MAX_DONORS = 200
CORE = 3


@dataclass(frozen=True)
class Treated:
    firm: int
    """Row of the firm in the panel."""
    event: int
    """Column of the event quarter: nothing from here on is read."""


def standardize(values: Floats) -> Floats:
    mean = np.nanmean(values, axis=0)
    std = np.nanstd(values, axis=0)
    return np.asarray((values - mean) / np.where(std > 0, std, 1.0))


def excluded_mask(
    panel: Panel,
    marks: dict[int, list[int]],
    margin: int,
    treated: Sequence[Treated] = (),
) -> np.ndarray:
    """[firms, quarters]: firm-quarters near a filing of the action, unusable as controls. A
    treated firm stays out for good from before its event, so the null never sees its
    results after the treatment either."""
    mask = np.zeros((len(panel.ciks), panel.quarters), dtype=bool)
    for firm, columns in marks.items():
        for column in columns:
            mask[firm, max(0, column - margin) : column + margin + 1] = True
    for event in treated:
        mask[event.firm, max(0, event.event - margin) :] = True
    return mask


def core_known(rows: Floats) -> np.ndarray:
    """Rows with size, growth and margin: what a match cannot do without."""
    return np.asarray(~np.isnan(rows[..., :CORE]).any(axis=-1))


def distances(rows: Floats, row: Floats, scale: Floats) -> Floats:
    """Mean squared gap over the covariates both rows have: debt is often missing."""
    gap = ((rows - row) / scale) ** 2
    known = ~np.isnan(gap)
    return np.asarray(np.where(known, gap, 0).sum(axis=-1) / np.maximum(known.sum(axis=-1), 1))


def scale_of(rows: Floats) -> Floats:
    std = np.nanstd(rows, axis=0)
    return np.asarray(np.where(std > 0, std, 1.0))


def match(panel: Panel, firm: int, column: int, excluded: np.ndarray) -> int | None:
    """The nearest firm of the same SIC division on covariates of one quarter, or None."""
    rows = panel.covariates[:, column]
    usable = core_known(rows) & ~excluded[:, column]
    usable[firm] = False
    same = usable & (np.array(panel.divisions) == panel.divisions[firm])
    pool = np.flatnonzero(same if same.any() else usable)
    if pool.size == 0 or not core_known(rows[firm]):
        return None
    return int(pool[np.argmin(distances(rows[pool], rows[firm], scale_of(rows)))])


def usable_events(panel: Panel, events: list[Treated]) -> list[Treated]:
    return [
        e
        for e in events
        if e.event - PRE_QUARTERS - WINDOW >= 0
        and core_known(panel.covariates[e.firm, e.event - 1])
    ]


def logistic(x: Floats, y: Floats, ridge: float = 1.0, steps: int = 25) -> Floats:
    """Propensity scores by Newton steps with a ridge, in plain numpy."""
    design = np.hstack([np.ones((x.shape[0], 1)), x])
    beta = np.zeros(design.shape[1])
    penalty = ridge * np.eye(design.shape[1])
    penalty[0, 0] = 0
    for _ in range(steps):
        p = 1 / (1 + np.exp(-np.clip(design @ beta, -30, 30)))
        gradient = design.T @ (y - p) - penalty @ beta
        hessian = (design * (p * (1 - p))[:, None]).T @ design + penalty
        beta = beta + np.linalg.solve(hessian, gradient)
    return np.asarray(1 / (1 + np.exp(-np.clip(design @ beta, -30, 30))))


def support_and_balance(
    panel: Panel, events: list[Treated], excluded: np.ndarray
) -> tuple[float | None, list[BalanceRow]]:
    """Share of treated inside the controls' propensity range, and differences of means."""
    if not events:
        return None, []
    treated = np.array([panel.covariates[e.firm, e.event - 1] for e in events])
    controls_list: list[Floats] = []
    matched_list: list[Floats] = []
    for e in events:
        column = e.event - 1
        rows = panel.covariates[:, column]
        keep = core_known(rows) & ~excluded[:, column]
        keep[e.firm] = False
        controls_list.append(rows[keep])
        partner = match(panel, e.firm, column, excluded)
        if partner is not None:
            matched_list.append(rows[partner])
    controls = np.vstack(controls_list)
    if controls.shape[0] < 2:
        return None, []
    together = np.nan_to_num(standardize(np.vstack([treated, controls])))
    labels = np.r_[np.ones(len(treated)), np.zeros(len(controls))]
    scores = logistic(together, labels)
    low, high = np.quantile(scores[labels == 0], (0.01, 0.99))
    inside = (scores[labels == 1] >= low) & (scores[labels == 1] <= high)
    pooled = np.nanstd(np.vstack([treated, controls]), axis=0)
    pooled = np.where(pooled > 0, pooled, 1.0)
    matched = np.array(matched_list) if matched_list else treated
    rows_out = [
        BalanceRow(
            covariate=name,
            before=float((np.nanmean(treated[:, k]) - np.nanmean(controls[:, k])) / pooled[k]),
            after=float((np.nanmean(treated[:, k]) - np.nanmean(matched[:, k])) / pooled[k]),
        )
        for k, name in enumerate(COVARIATES)
    ]
    return float(inside.mean()), rows_out


def _interval(values: Floats) -> tuple[float, float, float]:
    mean = float(values.mean())
    error = float(values.std(ddof=1) / np.sqrt(values.size)) if values.size > 1 else float("inf")
    return mean, mean - Z * error, mean + Z * error


def pre_trends(panel: Panel, events: list[Treated], excluded: np.ndarray) -> list[LeadRow]:
    """Treated minus matched control at each lead, against the quarter before the event."""
    rows: list[LeadRow] = []
    partners = {e: match(panel, e.firm, e.event - 1, excluded) for e in events}
    for k, name in enumerate(OUTCOMES):
        for lead in LEADS:
            gaps: list[float] = []
            for e in events:
                partner = partners[e]
                if partner is None:
                    continue
                base, then = e.event - 1, e.event + lead
                gap = (panel.outcomes[e.firm, then, k] - panel.outcomes[e.firm, base, k]) - (
                    panel.outcomes[partner, then, k] - panel.outcomes[partner, base, k]
                )
                if np.isfinite(gap):
                    gaps.append(float(gap))
            if len(gaps) >= 2:
                mean, low, high = _interval(np.array(gaps))
                rows.append(
                    LeadRow(
                        outcome=name, lead=lead, mean=mean, low=low, high=high, events=len(gaps)
                    )
                )
    return rows


def did(panel: Panel, firm: int, partner: int, column: int, outcome: int) -> float:
    """Change of the firm around a date, minus the change of its partner."""
    before = slice(column - WINDOW, column)
    after = slice(column, column + WINDOW)

    def change(row: int) -> float:
        series = panel.outcomes[row, :, outcome]
        if np.isnan(series[before]).all() or np.isnan(series[after]).all():
            return float("nan")
        return float(np.nanmean(series[after]) - np.nanmean(series[before]))

    return change(firm) - change(partner)


def placebo_dates(panel: Panel, events: list[Treated], excluded: np.ndarray) -> list[PlaceboRow]:
    """False events well before the true one: both windows end before the event quarter."""
    rows: list[PlaceboRow] = []
    for k, name in enumerate(OUTCOMES):
        for shift in SHIFTS:
            found: list[float] = []
            for e in events:
                column = e.event - shift
                if column - WINDOW < 0 or column + WINDOW > e.event:
                    continue
                partner = match(panel, e.firm, column - 1, excluded)
                if partner is None:
                    continue
                value = did(panel, e.firm, partner, column, k)
                if np.isfinite(value):
                    found.append(value)
            if len(found) >= 2:
                mean, low, high = _interval(np.array(found))
                rows.append(
                    PlaceboRow(
                        outcome=name,
                        shift=shift,
                        estimate=mean,
                        low=low,
                        high=high,
                        events=len(found),
                    )
                )
    return rows


def neighbours(panel: Panel, excluded: np.ndarray) -> list[tuple[int, int, int]]:
    """Every firm-quarter without the action and its nearest neighbour: column, firm, partner."""
    pairs: list[tuple[int, int, int]] = []
    for column in range(WINDOW + 1, panel.quarters - WINDOW):
        rows = panel.covariates[:, column - 1]
        pool = np.flatnonzero(core_known(rows) & ~excluded[:, column])
        if pool.size < 2:
            continue
        scale = scale_of(rows[pool])
        part = rows[pool]
        for i, firm in enumerate(pool):
            gaps = distances(part, part[i], scale)
            gaps[i] = np.inf
            pairs.append((column, int(firm), int(pool[np.argmin(gaps)])))
    return pairs


def pseudo_effects(panel: Panel, pairs: list[tuple[int, int, int]], outcome: int) -> Floats:
    """The estimate at every firm-quarter of firms without the action."""
    found = [did(panel, firm, partner, column, outcome) for column, firm, partner in pairs]
    values = np.array(found)
    return np.asarray(values[np.isfinite(values)])


def e_value(standardized: float) -> float:
    """VanderWeele's bound for a standardized effect: how strong hidden confounding must be."""
    ratio = float(np.exp(0.91 * abs(standardized)))
    return ratio + float(np.sqrt(ratio * (ratio - 1)))


def null_rows(
    panel: Panel, excluded: np.ndarray, count: int, pool: int, seed: int
) -> list[NullRow]:
    """What chance gives with as many pseudo-events as there are usable events."""
    rng = np.random.default_rng(seed)
    rows: list[NullRow] = []
    size = max(count, 2)
    pairs = neighbours(panel, excluded)
    for k, name in enumerate(OUTCOMES):
        effects = pseudo_effects(panel, pairs, k)
        if effects.size < size:
            continue
        low, high = np.quantile(effects, (0.01, 0.99))
        clipped = np.clip(effects, low, high)
        draws = rng.choice(clipped, size=(DRAWS, size))
        means = draws.mean(axis=1)
        errors = draws.std(axis=1, ddof=1) / np.sqrt(size)
        spread = float(clipped.std(ddof=1))
        minimum_now = POWER_FACTOR * spread / np.sqrt(size)
        rows.append(
            NullRow(
                outcome=name,
                draws=DRAWS,
                pseudo_events=count,
                spread=float(means.std(ddof=1)),
                false_positive_rate=float((np.abs(means / errors) > Z).mean()),
                minimum_effect_now=float(minimum_now),
                minimum_effect_pool=float(POWER_FACTOR * spread / np.sqrt(max(pool, 1))),
                e_value=e_value(float(minimum_now / spread)),
            )
        )
    return rows


def simplex_weights(donors: Floats, target: Floats, steps: int = 400) -> Floats:
    """Non-negative weights that add up to one, by projected gradient."""
    weights = np.full(donors.shape[1], 1 / donors.shape[1])
    rate = 1 / (np.linalg.norm(donors, 2) ** 2 + 1e-9)
    for _ in range(steps):
        weights = weights - rate * (donors.T @ (donors @ weights - target))
        ordered = np.sort(weights)[::-1]
        total = np.cumsum(ordered) - 1
        rank = np.arange(1, ordered.size + 1)
        last = rank[ordered - total / rank > 0][-1]
        weights = np.maximum(weights - total[last - 1] / last, 0)
    return weights


def synthetic_fit(panel: Panel, events: list[Treated], excluded: np.ndarray) -> SyntheticFit:
    """Fit on earlier pre-quarters, check on the last ones: all before the event."""
    span = FIT_QUARTERS + HOLDOUT_QUARTERS
    ratios: list[float] = []
    donors_seen: list[int] = []
    for e in events:
        start = e.event - span
        if start < 0:
            continue
        series = panel.outcomes[e.firm, start : e.event, 0]
        if np.isnan(series).any():
            continue
        window = panel.outcomes[:, start : e.event, 0]
        clean = ~np.isnan(window).any(axis=1) & ~excluded[:, start : e.event].any(axis=1)
        clean[e.firm] = False
        same = clean & (np.array(panel.divisions) == panel.divisions[e.firm])
        pool = np.flatnonzero(same)[:MAX_DONORS]
        if pool.size < MIN_DONORS:
            continue
        donors = window[pool].T
        weights = simplex_weights(donors[:FIT_QUARTERS], series[:FIT_QUARTERS])
        synthetic = donors @ weights
        gap = series - synthetic
        fit = float(np.sqrt((gap[:FIT_QUARTERS] ** 2).mean()))
        holdout = float(np.sqrt((gap[FIT_QUARTERS:] ** 2).mean()))
        donors_seen.append(int(pool.size))
        if fit > 0:
            ratios.append(holdout / fit)
    return SyntheticFit(
        usable=len(ratios),
        median_donors=float(np.median(donors_seen)) if donors_seen else 0.0,
        median_holdout_ratio=float(np.median(ratios)) if ratios else None,
    )
