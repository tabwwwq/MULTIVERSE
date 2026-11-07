"""Quantile forecasts: proper scores, coverage and conformal calibration (Stage 17).

All functions take quantiles ``q`` [rows, levels] and actuals ``y`` [rows] in one space.
The evaluation works in each target's training space (``to_target_space``): quantiles
survive a monotone map, and a margin of -30 000 no longer decides a mean of many firms.

- **Pinball** is the mean quantile loss over the levels; **WIS** is the weighted interval
  score (Bracher et al., 2021), the standard finite approximation of CRPS. Both are proper:
  a forecaster minimizes them by stating the true distribution.
- **Coverage** of a central interval is the share of actuals inside it, **width** its
  sharpness; a **reliability** curve is the share of actuals below each quantile.
- **Conformal calibration** (conformalized quantile regression, Romano et al., 2019): on
  rows the model never fitted, the score of a row is how far its actual lies outside the
  interval; the (1 - a)(1 + 1/n) empirical quantile of the scores widens (or narrows) that
  interval. The guarantee assumes calibration and new rows are exchangeable, which time
  series are not: the measured coverage on later years is what counts.
"""

import numpy as np

from multiverse_contracts.forecasting import ForecastTarget, LiveCompany
from multiverse_forecast.data import Bools, Floats, Texts

LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
NOMINAL = (0.5, 0.8, 0.9)
RATIO_SCALE = 0.1


def to_target_space(target: ForecastTarget, y: Floats) -> Floats:
    if target is ForecastTarget.REVENUE_GROWTH:
        return y
    if target is ForecastTarget.DEBT_TO_EBITDA:
        return np.arcsinh(y)
    return np.arcsinh(y / RATIO_SCALE)


def from_target_space(target: ForecastTarget, g: Floats) -> Floats:
    if target is ForecastTarget.REVENUE_GROWTH:
        return g
    if target is ForecastTarget.DEBT_TO_EBITDA:
        return np.sinh(g)
    return np.sinh(g) * RATIO_SCALE


def interval_columns(nominal: float, levels: tuple[float, ...] = LEVELS) -> tuple[int, int]:
    """The columns of the central interval of a nominal coverage."""
    tail = (1 - nominal) / 2
    low = min(range(len(levels)), key=lambda i: abs(levels[i] - tail))
    high = min(range(len(levels)), key=lambda i: abs(levels[i] - (1 - tail)))
    if abs(levels[low] - tail) > 1e-9 or abs(levels[high] - (1 - tail)) > 1e-9:
        raise ValueError(f"no levels for a central {nominal} interval")
    return low, high


def pinball_rows(q: Floats, y: Floats, levels: tuple[float, ...] = LEVELS) -> Floats:
    taus = np.asarray(levels)
    diff = y[:, None] - q
    return np.maximum(taus * diff, (taus - 1) * diff).mean(axis=1)


def wis_rows(q: Floats, y: Floats, levels: tuple[float, ...] = LEVELS) -> Floats:
    """Weighted interval score of the median and every central interval of the levels."""
    middle = len(levels) // 2
    if abs(levels[middle] - 0.5) > 1e-9 or len(levels) % 2 == 0:
        raise ValueError("WIS needs the median and symmetric levels")
    total = 0.5 * np.abs(y - q[:, middle])
    for low in range(middle):
        high = len(levels) - 1 - low
        alpha = 2 * levels[low]
        lower, upper = q[:, low], q[:, high]
        score = (upper - lower) + (2 / alpha) * (
            np.maximum(lower - y, 0) + np.maximum(y - upper, 0)
        )
        total = total + (alpha / 2) * score
    return total / (middle + 0.5)


def covered(q: Floats, y: Floats, nominal: float, levels: tuple[float, ...] = LEVELS) -> Bools:
    low, high = interval_columns(nominal, levels)
    return (y >= q[:, low]) & (y <= q[:, high])


def widths(q: Floats, nominal: float, levels: tuple[float, ...] = LEVELS) -> Floats:
    low, high = interval_columns(nominal, levels)
    return q[:, high] - q[:, low]


def reliability(q: Floats, y: Floats) -> Floats:
    """Per level, the share of actuals at or below the quantile; ideally the level itself."""
    return (y[:, None] <= q).mean(axis=0)


def conformal_offset(
    q: Floats, y: Floats, nominal: float, levels: tuple[float, ...] = LEVELS
) -> float:
    """How much to widen a central interval, from rows the model never fitted."""
    low, high = interval_columns(nominal, levels)
    scores = np.sort(np.maximum(q[:, low] - y, y - q[:, high]))
    rank = int(np.ceil(nominal * (scores.size + 1)))
    return float(scores[min(rank, scores.size) - 1])


def conformalize(
    q: Floats, offsets: dict[float, float], levels: tuple[float, ...] = LEVELS
) -> Floats:
    """Move each interval by its offset; the median stays; sorted so levels never cross."""
    out = np.array(q, copy=True)
    for nominal, offset in offsets.items():
        low, high = interval_columns(nominal, levels)
        out[:, low] -= offset
        out[:, high] += offset
    return np.sort(out, axis=1)


def firm_means(ciks: Texts, values: Floats) -> tuple[Floats, Floats]:
    """Sums and counts per firm, for a bootstrap that draws whole firms."""
    _, index = np.unique(ciks, return_inverse=True)
    return np.bincount(index, weights=values), np.bincount(index).astype(np.float64)


def firm_interval(ciks: Texts, values: Floats, resamples: int, seed: int) -> tuple[float, float]:
    """95% interval of a mean over rows, by a bootstrap over firms."""
    sums, counts = firm_means(ciks, values)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, sums.size, size=(resamples, sums.size))
    boot = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))


def firm_ratio_draws(ciks: Texts, mine: Floats, other: Floats, resamples: int, seed: int) -> Floats:
    """Bootstrap draws over firms of the mean of ``mine`` over the mean of ``other``."""
    sums, _ = firm_means(ciks, mine)
    other_sums, _ = firm_means(ciks, other)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, sums.size, size=(resamples, sums.size))
    return np.asarray(sums[draws].sum(axis=1) / other_sums[draws].sum(axis=1))


def ratio_interval(
    ciks: Texts, mine: Floats, other: Floats, resamples: int, seed: int
) -> tuple[float, float, float]:
    """Mean of ``mine`` over mean of ``other``, minus one, with its firm-bootstrap interval."""
    boot = firm_ratio_draws(ciks, mine, other, resamples, seed) - 1
    return (
        float(mine.mean() / other.mean() - 1),
        float(np.quantile(boot, 0.025)),
        float(np.quantile(boot, 0.975)),
    )


def median_of(company: LiveCompany, target: ForecastTarget, horizon: int) -> float | None:
    """The median of a live band; without PyTorch, so that a case can read it."""
    middle = len(LEVELS) // 2
    for band in company.bands:
        if band.target is target and band.horizon == horizon:
            return band.values[middle]
    return None
