"""Errors of one model on one set of rows: point scores and intervals (Stage 15).

Rows are forecast examples of many firms, and examples of one firm are correlated, so the
95% intervals come from a bootstrap over firms: firms are drawn with replacement and all
their rows come along. ``vs_naive`` is the model's MAE over the persistence MAE on the
same rows, minus one: below zero the model beats persistence.
"""

from dataclasses import dataclass

import numpy as np

from multiverse_contracts.forecasting import (
    ForecastTarget,
    Population,
    ScoreRow,
    SectorScore,
    SplitName,
)
from multiverse_forecast.data import Floats, Texts


@dataclass(frozen=True)
class Errors:
    ciks: Texts
    divisions: Texts
    weights: Floats
    """Trailing four-quarter revenue at the origin; zero where unknown."""
    actual: Floats
    predicted: Floats
    naive: Floats


def _company_sums(ciks: Texts, values: Floats) -> tuple[Floats, Floats]:
    _, index = np.unique(ciks, return_inverse=True)
    sums = np.bincount(index, weights=values)
    counts = np.bincount(index).astype(np.float64)
    return sums, counts


def score(
    target: ForecastTarget,
    horizon: int,
    split: SplitName,
    model: str,
    errors: Errors,
    resamples: int,
    seed: int,
    population: Population = Population.ALL,
) -> ScoreRow:
    error = errors.predicted - errors.actual
    absolute = np.abs(error)
    naive_abs = np.abs(errors.naive - errors.actual)
    mae = float(absolute.mean())
    naive_mae = float(naive_abs.mean())
    sums, counts = _company_sums(errors.ciks, absolute)
    naive_sums, _ = _company_sums(errors.ciks, naive_abs)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(sums), size=(resamples, len(sums)))
    boot = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    boot_naive = naive_sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    weight = errors.weights.sum()
    total_actual = float(np.abs(errors.actual).sum())
    relative: dict[str, float | None] = {
        "vs_naive": None,
        "vs_naive_low": None,
        "vs_naive_high": None,
    }
    if naive_mae > 0 and np.all(boot_naive > 0):
        ratio = boot / boot_naive - 1
        relative = {
            "vs_naive": mae / naive_mae - 1,
            "vs_naive_low": float(np.quantile(ratio, 0.025)),
            "vs_naive_high": float(np.quantile(ratio, 0.975)),
        }
    return ScoreRow(
        target=target,
        horizon=horizon,
        split=split,
        population=population,
        model=model,
        examples=int(absolute.size),
        companies=len(sums),
        mae=mae,
        rmse=float(np.sqrt(np.mean(error**2))),
        median_ae=float(np.median(absolute)),
        wape=float(absolute.sum() / total_actual) if total_actual > 0 else None,
        firm_weighted_mae=float(np.mean(sums / counts)),
        revenue_weighted_mae=float((absolute * errors.weights).sum() / weight)
        if weight > 0
        else mae,
        mae_low=float(np.quantile(boot, 0.025)),
        mae_high=float(np.quantile(boot, 0.975)),
        **relative,
    )


def sector_scores(
    target: ForecastTarget, horizon: int, split: SplitName, model: str, errors: Errors
) -> list[SectorScore]:
    absolute = np.abs(errors.predicted - errors.actual)
    found = []
    for division in sorted(set(errors.divisions.tolist())):
        mine = errors.divisions == division
        found.append(
            SectorScore(
                target=target,
                horizon=horizon,
                split=split,
                model=model,
                division=str(division),
                examples=int(mine.sum()),
                mae=float(absolute[mine].mean()),
            )
        )
    return found
