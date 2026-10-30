"""Trainable examples: how much of the dataset a forecasting model can actually use.

An example is a company and a forecast origin (a calendar quarter end) with

- a history: the last ``H`` quarters before the origin (lags 1 to H) all hold the target
  metric in the point-in-time panel at the origin (vintage view: only what was public);
- a target: the metric of the quarter ``h`` quarters after the origin, as first released
  (original view), released by the data cutoff.

Lag 0, the quarter ending on the origin, is never part of the history: its report is
not public yet. Counts are given for H = 8, 12, 20 and h = 1, 4, 8, 12, 20 (docs/06).
"""

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from multiverse_contracts.normalized import FiscalPeriod
from multiverse_contracts.pit import KnowledgeView
from multiverse_contracts.quality import ExampleCount
from multiverse_pipelines.pit.clock import day_end
from multiverse_pipelines.pit.panel import build_panel, nearest_quarter_end, quarter_ends
from multiverse_pipelines.pit.warehouse import Warehouse

HISTORIES = (8, 12, 20)
HORIZONS = (1, 4, 8, 12, 20)
QUARTERS = (FiscalPeriod.Q1, FiscalPeriod.Q2, FiscalPeriod.Q3, FiscalPeriod.Q4)


def shift(end: date, quarters: int) -> date:
    """The calendar quarter end ``quarters`` quarters after another one."""
    index = end.year * 4 + (end.month - 1) // 3 + quarters
    year, number = divmod(index, 4)
    month = 3 * (number + 1)
    return date(year, month, 31 if month in (3, 12) else 30)


def origins(first: date, last: date) -> list[date]:
    found, end = [], nearest_quarter_end(first)
    while end <= last:
        found.append(end)
        end = shift(end, 1)
    return found


@dataclass(frozen=True)
class Example:
    cik: str
    origin: date
    history: int
    horizon: int
    target_quarter: date
    target: str


def targets(
    warehouse: Warehouse, ciks: Sequence[str], metric: str, data_cutoff: datetime
) -> dict[tuple[str, date], str]:
    """Each company quarter's metric as first released, among releases by the data cutoff."""
    found: dict[tuple[str, date], str] = {}
    for cik in ciks:
        for item in warehouse.as_of(cik, data_cutoff, view=KnowledgeView.ORIGINAL, metric=metric):
            row = item.value
            if row.fiscal_period in QUARTERS and row.value is not None:
                found[(cik, nearest_quarter_end(row.period_end))] = row.value
    return found


def count_examples(
    warehouse: Warehouse,
    ciks: Sequence[str],
    metric: str,
    data_cutoff: datetime,
    first_origin: date,
) -> tuple[list[ExampleCount], list[Example]]:
    goal = targets(warehouse, ciks, metric, data_cutoff)
    last_origin = quarter_ends(data_cutoff.date(), 1)[0]
    examples: list[Example] = []
    longest = max(HISTORIES)
    for origin in origins(first_origin, last_origin):
        panel = build_panel(
            warehouse, ciks, day_end(origin), quarters=longest + 1, metrics=(metric,)
        )
        masks: dict[str, list[bool]] = defaultdict(lambda: [False] * (longest + 1))
        for cell in panel.cells:
            masks[cell.cik][cell.lag] = cell.mask
        for cik in sorted(masks):
            for history in HISTORIES:
                if not all(masks[cik][1 : history + 1]):
                    continue
                for horizon in HORIZONS:
                    quarter = shift(origin, horizon)
                    value = goal.get((cik, quarter))
                    if value is not None:
                        examples.append(Example(cik, origin, history, horizon, quarter, value))
    counts = []
    for history in HISTORIES:
        for horizon in HORIZONS:
            chosen = [e for e in examples if e.history == history and e.horizon == horizon]
            counts.append(
                ExampleCount(
                    history_quarters=history,
                    horizon_quarters=horizon,
                    examples=len(chosen),
                    companies=len({e.cik for e in chosen}),
                    origins=len({e.origin for e in chosen}),
                )
            )
    return counts, examples


def examples_hash(examples: Sequence[Example]) -> str:
    lines = [
        json.dumps(
            [
                e.cik,
                e.origin.isoformat(),
                e.history,
                e.horizon,
                e.target_quarter.isoformat(),
                e.target,
            ],
            separators=(",", ":"),
        )
        for e in sorted(examples, key=lambda e: (e.cik, e.origin, e.history, e.horizon))
    ]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()
