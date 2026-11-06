"""The panel the diagnostics read: firms by quarters, as public at each origin (Stage 15).

Quarters are indexed year * 4 + quarter. The panel knows nothing of events. A diagnostic reads
it only through ``before`` and through firms without the action, so a treated firm's outcome
at or after its event quarter is never touched: the study stays blind to the effect.
"""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import numpy.typing as npt

Floats = npt.NDArray[np.float64]
RATIO_SCALE = 0.1
OUTCOMES = ("rev_growth_l1", "op_margin_l1", "fcf_margin_l1")
COVARIATES = (
    "log_rev_ttm",
    "rev_growth_l1",
    "op_margin_l1",
    "fcf_margin_l1",
    "capex_intensity_ttm",
    "cash_to_rev_ttm",
    "net_debt_to_rev_ttm",
)
SCALED = {"op_margin_l1", "fcf_margin_l1", "capex_intensity_ttm", "cash_to_rev_ttm"}


def quarter_of(day: date) -> int:
    return day.year * 4 + (day.month - 1) // 3


def number(text: str) -> float:
    return float(text) if text and text != "undefined" else float("nan")


@dataclass(frozen=True)
class Panel:
    ciks: tuple[str, ...]
    divisions: tuple[str, ...]
    first: int
    """The quarter of column 0."""
    outcomes: Floats
    """[firms, quarters, outcomes]; ratios through asinh, so a few extremes cannot rule."""
    covariates: Floats
    """[firms, quarters, covariates]; NaN when missing."""

    @property
    def quarters(self) -> int:
        return int(self.outcomes.shape[1])

    def column(self, quarter: int) -> int:
        return quarter - self.first

    def index(self, cik: str) -> int | None:
        return self.ciks.index(cik) if cik in self.ciks else None


def _transform(name: str, value: float) -> float:
    return float(np.arcsinh(value / RATIO_SCALE)) if name in SCALED else value


def load_panel(dataset_csv: Path) -> Panel:
    rows: list[tuple[str, str, int, dict[str, str]]] = []
    with dataset_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            quarter = quarter_of(date.fromisoformat(row["origin"]))
            rows.append((row["cik"], row["division"], quarter, row))
    firms = sorted({r[0] for r in rows})
    position = {cik: i for i, cik in enumerate(firms)}
    first = min(r[2] for r in rows)
    last = max(r[2] for r in rows)
    shape = (len(firms), last - first + 1)
    outcomes = np.full((*shape, len(OUTCOMES)), np.nan)
    covariates = np.full((*shape, len(COVARIATES)), np.nan)
    divisions = [""] * len(firms)
    for cik, division, quarter, row in rows:
        i, t = position[cik], quarter - first
        divisions[i] = division
        for k, name in enumerate(OUTCOMES):
            outcomes[i, t, k] = _transform(name, number(row[name]))
        for k, name in enumerate(COVARIATES):
            covariates[i, t, k] = _transform(name, number(row[name]))
    return Panel(tuple(firms), tuple(divisions), first, outcomes, covariates)
