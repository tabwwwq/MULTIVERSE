"""Quarterly histories for the temporal model of Stage 16: 24 quarters per origin.

For every row of a Stage 15 dataset (a company and a forecast origin), the point-in-time
panel at the origin gives nine channels for each lag 1 to 24; lag 0, the quarter ending on
the origin, is never public. A missing value is an empty cell: the model reads it as a
mask, never as a zero. The rows are exactly the dataset's rows, so Stage 16 is scored on
what Stage 15 was scored on.
"""

import csv
import io
import math
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from multiverse_pipelines.forecastset.build import (
    METRICS,
    _debt,
    _growth,
    _ratio,
    _sum,
    _text,
    _warehouse,
)
from multiverse_pipelines.pit.clock import day_end
from multiverse_pipelines.pit.panel import build_panel

SEQUENCE_LAGS = 24
# Growth needs the quarter a year earlier; the debt multiple the three before.
PANEL_QUARTERS = SEQUENCE_LAGS + 5
CHANNELS = (
    "rev_growth",
    "log_rev",
    "op_margin",
    "ebitda_margin",
    "fcf_margin",
    "capex_intensity",
    "rnd_intensity",
    "cash_to_rev",
    "debt_to_ebitda",
)
Lagged = dict[tuple[str, int], Decimal]
SequenceRow = tuple[str, str, int, list[float | None]]


def channels_at(lagged: Lagged, lag: int) -> list[float | None]:
    """The nine channels of one quarter, as known at the origin."""

    def v(metric: str, k: int = lag) -> Decimal | None:
        return lagged.get((metric, k))

    revenue = v("revenue")
    trailing = _sum(v("revenue", k) for k in range(lag, lag + 4))
    ebitda = _sum(v("ebitda", k) for k in range(lag, lag + 4))
    return [
        _growth(revenue, v("revenue", lag + 4)),
        math.log(revenue) if revenue is not None and revenue > 0 else None,
        _ratio(v("operating_income"), revenue),
        _ratio(v("ebitda"), revenue),
        _ratio(v("free_cash_flow"), revenue),
        _ratio(v("capex"), revenue),
        _ratio(v("rnd"), revenue),
        _ratio(v("cash"), trailing),
        _ratio(_debt(lambda metric: v(metric)), ebitda),
    ]


@dataclass(frozen=True)
class SequenceTask:
    db_path: Path
    cik: str
    origins: tuple[date, ...]


def company_sequences(task: SequenceTask) -> list[SequenceRow]:
    """Every lag of every wanted origin of one company (runs in a worker process)."""
    warehouse = _warehouse(task.db_path)
    rows: list[SequenceRow] = []
    for origin in task.origins:
        panel = build_panel(
            warehouse, [task.cik], day_end(origin), quarters=PANEL_QUARTERS, metrics=METRICS
        )
        lagged = {
            (c.metric, c.lag): Decimal(c.value)
            for c in panel.cells
            if c.mask and c.value is not None and c.lag >= 1
        }
        for lag in range(1, SEQUENCE_LAGS + 1):
            rows.append((task.cik, origin.isoformat(), lag, channels_at(lagged, lag)))
    return rows


def build_sequences(
    db_path: Path,
    wanted: dict[str, list[date]],
    workers: int,
    progress: Callable[[int, int], None] | None = None,
) -> list[SequenceRow]:
    tasks = [SequenceTask(db_path, cik, tuple(sorted(wanted[cik]))) for cik in sorted(wanted)]
    rows: list[SequenceRow] = []
    if workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(min(workers, len(tasks))) as pool:
            for number, found in enumerate(pool.map(company_sequences, tasks), start=1):
                rows += found
                if progress is not None:
                    progress(number, len(tasks))
    else:
        for number, task in enumerate(tasks, start=1):
            rows += company_sequences(task)
            if progress is not None:
                progress(number, len(tasks))
    return rows


def to_sequence_csv(rows: Sequence[SequenceRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("cik", "origin", "lag", *CHANNELS))
    for cik, origin, lag, values in sorted(rows, key=lambda r: (r[0], r[1], r[2])):
        writer.writerow([cik, origin, lag, *(_text(v) for v in values)])
    return buffer.getvalue()


def dataset_rows(folder: Path) -> dict[str, list[date]]:
    """The company origins of a Stage 15 dataset folder."""
    wanted: dict[str, list[date]] = {}
    with (folder / "dataset.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            wanted.setdefault(row["cik"], []).append(date.fromisoformat(row["origin"]))
    return wanted
