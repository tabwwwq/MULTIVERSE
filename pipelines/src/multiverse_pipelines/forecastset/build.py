"""The forecasting dataset: one row per company and forecast origin (Stage 15).

Features are what the point-in-time panel held at the origin (vintage view, lags 1 to 8;
lag 0, the quarter ending on the origin, is never public yet). Targets are the target
quarter's values as first released, each with the moment it was released, so a model
trains on a row only once its target was public. Macro features are each series' latest
value available at the origin. Every model of Stage 15 reads these same rows.

Targets of quarter q (calendar quarter, as the panel places fiscal quarters):

- revenue_growth: symmetric growth over the same quarter a year earlier,
  (a - b) / ((a + b) / 2), between -2 and 2; undefined when a revenue is negative or both
  are zero. The plain ratio a / b - 1 explodes on a tiny base (one firm's -9 189, that is
  -918 900%) and lets a few near-zero revenues decide every error measure;
- operating, EBITDA and FCF margins: the metric over revenue(q), undefined when revenue
  is not positive;
- debt_to_ebitda: debt at the end of q over EBITDA of q - 3 .. q, undefined when that
  EBITDA is not positive. Debt is long-term debt, or its noncurrent part plus current debt.

A row is kept when the company had revenue in one of the last four quarters at the
origin: without it no model has anything to start from.
"""

import csv
import hashlib
import io
import math
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from multiverse_contracts.forecasting import ForecastTarget, TargetCount
from multiverse_contracts.normalized import FiscalPeriod
from multiverse_contracts.pit import KnowledgeView
from multiverse_pipelines.audit.examples import shift
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.clock import day_end, stamp
from multiverse_pipelines.pit.panel import build_panel, nearest_quarter_end
from multiverse_pipelines.pit.warehouse import Warehouse

METRICS = (
    "revenue",
    "operating_income",
    "ebitda",
    "free_cash_flow",
    "capex",
    "rnd",
    "cash",
    "long_term_debt",
    "long_term_debt_noncurrent",
    "debt_current",
)
HORIZONS = (1, 4, 8, 12, 20)
LAGS = 8
FIRST_ORIGIN = date(2010, 3, 31)
QUARTERS = (FiscalPeriod.Q1, FiscalPeriod.Q2, FiscalPeriod.Q3, FiscalPeriod.Q4)
MARGINS = {
    ForecastTarget.OPERATING_MARGIN: "operating_income",
    ForecastTarget.EBITDA_MARGIN: "ebitda",
    ForecastTarget.FCF_MARGIN: "free_cash_flow",
}
# Macro features: (name, series, transform). "level" is the latest period's value;
# "yoy" compares it with the period a year earlier in the same release.
MACRO = (
    ("macro_fedfunds", "fred:FEDFUNDS", "level"),
    ("macro_cpi_yoy", "fred:CPIAUCSL", "yoy"),
    ("macro_unrate", "fred:UNRATE", "level"),
    ("macro_gdp_yoy", "fred:GDPC1", "yoy"),
    ("macro_ust10y", "fred:DGS10", "level"),
    ("macro_term_spread", "fred:T10Y2Y", "level"),
    ("macro_recession", "fred:USREC", "level"),
    ("macro_eurusd", "ecb:EXR.D.USD.EUR.SP00.A", "level"),
    ("macro_ecb_dfr", "ecb:FM.D.U2.EUR.4F.KR.DFR.LEV", "level"),
    ("macro_ea10y", "ecb:YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", "level"),
)
COMPANY_FEATURES = (
    *(f"rev_growth_l{k}" for k in range(1, 5)),
    "log_rev_ttm",
    *(f"op_margin_l{k}" for k in range(1, 5)),
    *(f"ebitda_margin_l{k}" for k in range(1, 5)),
    *(f"fcf_margin_l{k}" for k in range(1, 5)),
    "fcf_margin_ttm",
    "capex_intensity_ttm",
    "rnd_intensity_ttm",
    "cash_to_rev_ttm",
    "debt_to_ebitda_l1",
    "net_debt_to_rev_ttm",
    "history_quarters",
    "origin_quarter",
)
FEATURES = (*COMPANY_FEATURES, *(name for name, _, _ in MACRO))
META = ("cik", "origin", "division", "rev_ttm")
UNDEFINED = "undefined"
Value = float | str | None
Row = dict[str, Value]
Released = tuple[Decimal, datetime]


def target_columns() -> list[str]:
    columns = []
    for target in ForecastTarget:
        for horizon in HORIZONS:
            columns += [f"y_{target.value}_h{horizon}", f"r_{target.value}_h{horizon}"]
    return columns


def _ratio(top: Decimal | None, bottom: Decimal | None) -> float | None:
    if top is None or bottom is None or bottom <= 0:
        return None
    return float(top / bottom)


def _growth(now: Decimal | None, before: Decimal | None) -> float | None:
    """Symmetric growth: (now - before) / their mean, between -2 and 2."""
    if now is None or before is None or now < 0 or before < 0 or now + before == 0:
        return None
    return float(2 * (now - before) / (now + before))


def _sum(values: Iterable[Decimal | None]) -> Decimal | None:
    items = list(values)
    if any(v is None for v in items):
        return None
    return sum((v for v in items if v is not None), Decimal(0))


def _debt(get: Callable[[str], Decimal | None]) -> Decimal | None:
    total = get("long_term_debt")
    if total is not None:
        return total
    noncurrent = get("long_term_debt_noncurrent")
    if noncurrent is None:
        return None
    return noncurrent + (get("debt_current") or Decimal(0))


def features_at(lagged: dict[tuple[str, int], Decimal], origin: date) -> Row:
    """Company features from the panel at the origin: lags 1 to 8, never lag 0."""

    def v(metric: str, lag: int) -> Decimal | None:
        return lagged.get((metric, lag))

    row: Row = {}
    for k in range(1, 5):
        row[f"rev_growth_l{k}"] = _growth(v("revenue", k), v("revenue", k + 4))
        for name, metric in (
            ("op", "operating_income"),
            ("ebitda", "ebitda"),
            ("fcf", "free_cash_flow"),
        ):
            row[f"{name}_margin_l{k}"] = _ratio(v(metric, k), v("revenue", k))
    revenue = _sum(v("revenue", k) for k in range(1, 5))
    row["log_rev_ttm"] = math.log(revenue) if revenue is not None and revenue > 0 else None
    for name, metric in (
        ("fcf_margin_ttm", "free_cash_flow"),
        ("capex_intensity_ttm", "capex"),
        ("rnd_intensity_ttm", "rnd"),
    ):
        row[name] = _ratio(_sum(v(metric, k) for k in range(1, 5)), revenue)
    row["cash_to_rev_ttm"] = _ratio(v("cash", 1), revenue)
    debt = _debt(lambda metric: v(metric, 1))
    row["debt_to_ebitda_l1"] = _ratio(debt, _sum(v("ebitda", k) for k in range(1, 5)))
    cash = v("cash", 1)
    row["net_debt_to_rev_ttm"] = (
        _ratio(debt - cash, revenue) if debt is not None and cash is not None else None
    )
    row["history_quarters"] = float(sum(v("revenue", k) is not None for k in range(1, LAGS + 1)))
    row["origin_quarter"] = float((origin.month - 1) // 3 + 1)
    row["rev_ttm"] = float(revenue) if revenue is not None and revenue > 0 else None
    return row


def released_values(
    warehouse: Warehouse, cik: str, data_cutoff: datetime
) -> dict[tuple[str, date], Released]:
    """Each metric and calendar quarter as first released, with its release moment."""
    found: dict[tuple[str, date], Released] = {}
    for item in warehouse.as_of(cik, data_cutoff, view=KnowledgeView.ORIGINAL):
        row = item.value
        if row.metric not in METRICS or row.fiscal_period not in QUARTERS or row.value is None:
            continue
        found[(row.metric, nearest_quarter_end(row.period_end))] = (
            Decimal(row.value),
            item.known_from,
        )
    return found


def targets_for(
    released: dict[tuple[str, date], Released], quarter: date
) -> dict[ForecastTarget, tuple[Value, datetime | None]]:
    """Each target of one quarter: its value (or "undefined") and when it was public."""

    def get(metric: str, q: date = quarter) -> Released | None:
        return released.get((metric, q))

    def when(*items: Released | None) -> datetime:
        return max(item[1] for item in items if item is not None)

    found: dict[ForecastTarget, tuple[Value, datetime | None]] = {}
    revenue, earlier = get("revenue"), get("revenue", shift(quarter, -4))
    if revenue is not None and earlier is not None:
        growth = _growth(revenue[0], earlier[0])
        found[ForecastTarget.REVENUE_GROWTH] = (
            (growth if growth is not None else UNDEFINED),
            when(revenue, earlier),
        )
    for target, metric in MARGINS.items():
        part = get(metric)
        if revenue is not None and part is not None:
            ratio = _ratio(part[0], revenue[0])
            found[target] = (ratio if ratio is not None else UNDEFINED, when(revenue, part))
    window = [get("ebitda", shift(quarter, -k)) for k in range(4)]
    debt_items = {
        m: get(m) for m in ("long_term_debt", "long_term_debt_noncurrent", "debt_current")
    }

    def amount(metric: str) -> Decimal | None:
        item = debt_items[metric]
        return item[0] if item is not None else None

    debt = _debt(amount)
    if debt is not None and all(w is not None for w in window):
        ttm = sum((w[0] for w in window if w is not None), Decimal(0))
        used = [d for d in debt_items.values() if d is not None]
        found[ForecastTarget.DEBT_TO_EBITDA] = (
            float(debt / ttm) if ttm > 0 else UNDEFINED,
            when(*window, *used),
        )
    return found


@dataclass(frozen=True)
class CompanyTask:
    db_path: Path
    cik: str
    division: str
    origins: tuple[date, ...]
    data_cutoff: datetime


_OPEN: dict[Path, Warehouse] = {}


def _warehouse(path: Path) -> Warehouse:
    if path not in _OPEN:
        _OPEN[path] = Warehouse.open(path)
    return _OPEN[path]


def company_rows(task: CompanyTask) -> list[Row]:
    """Every kept origin of one company (runs in a worker process)."""
    warehouse = _warehouse(task.db_path)
    released = released_values(warehouse, task.cik, task.data_cutoff)
    rows: list[Row] = []
    for origin in task.origins:
        panel = build_panel(
            warehouse, [task.cik], day_end(origin), quarters=LAGS + 1, metrics=METRICS
        )
        lagged = {
            (c.metric, c.lag): Decimal(c.value)
            for c in panel.cells
            if c.mask and c.value is not None and c.lag >= 1
        }
        if not any(("revenue", k) in lagged for k in range(1, 5)):
            continue
        row: Row = {"cik": task.cik, "origin": origin.isoformat(), "division": task.division}
        row |= features_at(lagged, origin)
        for horizon in HORIZONS:
            found = targets_for(released, shift(origin, horizon))
            for target in ForecastTarget:
                value, public = found.get(target, (None, None))
                row[f"y_{target.value}_h{horizon}"] = value
                row[f"r_{target.value}_h{horizon}"] = stamp(public) if public else None
        rows.append(row)
    return rows


def macro_features(store: MacroStore | None, origins: Sequence[date]) -> dict[date, Row]:
    """Each series' latest value available at the end of each origin day."""
    found: dict[date, Row] = {}
    for origin in origins:
        row: Row = {}
        for name, series, transform in MACRO:
            row[name] = None
            if store is None:
                continue
            available = store.as_of(series, day_end(origin))
            values = {k: o.value for k, o in available.items() if o.value is not None}
            if not values:
                continue
            last = max(values)
            if transform == "level":
                row[name] = float(Decimal(values[last]))
                continue
            earlier = date(last.year - 1, last.month, last.day)
            if earlier in values and Decimal(values[earlier]) != 0:
                row[name] = float(Decimal(values[last]) / Decimal(values[earlier]) - 1)
        found[origin] = row
    return found


def build_rows(
    db_path: Path,
    divisions: dict[str, str],
    origins: Sequence[date],
    data_cutoff: datetime,
    workers: int,
    progress: Callable[[int, int], None] | None = None,
) -> list[Row]:
    tasks = [
        CompanyTask(db_path, cik, divisions[cik], tuple(origins), data_cutoff)
        for cik in sorted(divisions)
    ]
    rows: list[Row] = []
    if workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(min(workers, len(tasks))) as pool:
            for number, found in enumerate(pool.map(company_rows, tasks), start=1):
                rows += found
                if progress is not None:
                    progress(number, len(tasks))
    else:
        for number, task in enumerate(tasks, start=1):
            rows += company_rows(task)
            if progress is not None:
                progress(number, len(tasks))
    return rows


def _text(value: Value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".10g")
    return value


def to_csv(rows: Sequence[Row], macro: dict[date, Row]) -> str:
    columns = [*META, *FEATURES, *target_columns()]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in sorted(rows, key=lambda r: (str(r["cik"]), str(r["origin"]))):
        full = row | macro.get(date.fromisoformat(str(row["origin"])), {})
        writer.writerow([_text(full.get(column)) for column in columns])
    return buffer.getvalue()


def target_counts(rows: Sequence[Row]) -> list[TargetCount]:
    counts = []
    for target in ForecastTarget:
        for horizon in HORIZONS:
            values = [row.get(f"y_{target.value}_h{horizon}") for row in rows]
            counts.append(
                TargetCount(
                    target=target,
                    horizon=horizon,
                    defined=sum(isinstance(v, float) for v in values),
                    undefined=sum(v == UNDEFINED for v in values),
                )
            )
    return counts


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_rows(text: str, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "dataset.csv"
    path.write_bytes(text.encode("utf-8"))
    return path


def kept(origins: Iterable[date], rows: Sequence[Row]) -> tuple[date, date]:
    used = sorted({date.fromisoformat(str(r["origin"])) for r in rows}) or sorted(origins)
    return used[0], used[-1]
