"""Exogenous shocks: a stationary block bootstrap of calendar quarters.

A draw takes a whole row of the history: macro, sector and firm columns of one quarter together,
so their links survive without a covariance model. Blocks of consecutive quarters keep the
temporal dependence (Politis and Romano, 1994). The rows are residuals, so a draw is a residual
bootstrap; growth and margin deviations then decay at the persistence of the case.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from multiverse_contracts.simulation import ShockHistory, SimulationSettings

Floats = npt.NDArray[np.float64]
RATE = "rate_change"
MACRO = (RATE, "gdp_change")
SECTOR_GROWTH, FIRM_GROWTH = "sector_growth", "firm_growth"
SECTOR_MARGIN, FIRM_MARGIN = "sector_margin", "firm_margin"
REQUIRED = (RATE, SECTOR_GROWTH, FIRM_GROWTH, SECTOR_MARGIN, FIRM_MARGIN)


@dataclass(frozen=True)
class PathShocks:
    """What one path is exposed to, by quarter. All of it is shared by baseline and alternate."""

    growth: Floats
    margin: Floats
    rate_shift: Floats
    drawn: Floats
    """The rows drawn: [quarters, variables]."""


def _without_macro(table: Floats, names: tuple[str, ...]) -> Floats:
    """Macro columns at zero, and sector columns without the part macro explains."""
    macro = [names.index(name) for name in MACRO if name in names]
    locked = table.copy()
    for name in (SECTOR_GROWTH, SECTOR_MARGIN):
        column = names.index(name)
        fit, *_ = np.linalg.lstsq(table[:, macro], table[:, column], rcond=None)
        locked[:, column] = table[:, column] - table[:, macro] @ fit
    locked[:, macro] = 0.0
    return locked


@dataclass(frozen=True)
class ShockModel:
    names: tuple[str, ...]
    table: Floats
    """[quarters of history, variables], each column centred: a shock has no drift."""
    persistence_growth: float
    persistence_margin: float
    mean_block: float
    base_short_rate: float

    @classmethod
    def of(cls, history: ShockHistory, settings: SimulationSettings) -> "ShockModel":
        missing = set(REQUIRED) - set(history.variables)
        if missing:
            raise ValueError(f"the shock history lacks {sorted(missing)}")
        table = np.array([row.values for row in history.rows], dtype=np.float64)
        table = (table - table.mean(axis=0)) * settings.shock_scale
        if settings.lock_macro:
            table = _without_macro(table, history.variables)
        return cls(
            history.variables,
            table,
            history.persistence_growth,
            history.persistence_margin,
            settings.mean_block_quarters or history.mean_block_quarters,
            history.base_short_rate,
        )

    def column(self, name: str) -> int:
        return self.names.index(name)


def block_indices(
    rng: np.random.Generator, rows: int, quarters: int, mean_block: float
) -> npt.NDArray[np.int64]:
    """Rows of the history for one path: a block ends each quarter with probability 1 / L."""
    starts = rng.integers(rows, size=quarters)
    fresh = rng.random(quarters) < 1.0 / mean_block
    chosen = np.empty(quarters, dtype=np.int64)
    chosen[0] = starts[0]
    for quarter in range(1, quarters):
        chosen[quarter] = starts[quarter] if fresh[quarter] else (chosen[quarter - 1] + 1) % rows
    return chosen


def _decayed(innovations: Floats, persistence: float) -> Floats:
    """D_h = φ D_{h−1} + ε_h, from zero: the central path is where the company stands today."""
    deviation = np.empty_like(innovations)
    level = 0.0
    for quarter, innovation in enumerate(innovations):
        level = persistence * level + float(innovation)
        deviation[quarter] = level
    return deviation


def draw(model: ShockModel, rng: np.random.Generator, quarters: int) -> PathShocks:
    """One path of shocks. Short rates walk and stop at zero; growth and margin revert."""
    rows = model.table[block_indices(rng, len(model.table), quarters, model.mean_block)]
    growth = rows[:, model.column(SECTOR_GROWTH)] + rows[:, model.column(FIRM_GROWTH)]
    margin = rows[:, model.column(SECTOR_MARGIN)] + rows[:, model.column(FIRM_MARGIN)]
    walk = np.cumsum(rows[:, model.column(RATE)])
    return PathShocks(
        _decayed(growth, model.persistence_growth),
        _decayed(margin, model.persistence_margin),
        np.maximum(walk, -model.base_short_rate),
        rows,
    )
