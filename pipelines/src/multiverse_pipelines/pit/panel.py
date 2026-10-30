"""The as-of quarterly panel: every company, calendar quarter and metric at one cutoff.

Rows are calendar quarters, so companies with different fiscal years line up: a fiscal
quarter belongs to the calendar quarter whose end is nearest to its own end (a quarter
ending 2 January belongs to the fourth quarter, one ending 31 January too). The panel is
complete: each company has a cell for each of the last ``quarters`` calendar quarters
ended at the cutoff and each metric, whether or not a value was knowable.

Cell states, in the order they are decided:

1. ``inactive``      the company had filed a Form 15 before the quarter ended, no
                     periodic report followed it, and the report for the first quarter
                     after the Form 15 is overdue (more than 90 days) at the cutoff. A
                     Form 15 can end the registration of one class of securities only;
                     until that report is overdue the quarter is ``not_yet_filed``;
2. ``observed`` / ``derived``  a value public at the cutoff (reported, or computed from
                     reported values that were all public);
3. ``blocked``       the value is withheld (conflicting values in one filing);
4. ``not_covered``   before the first XBRL report, or no XBRL 10-K yet to place quarters;
5. ``not_reported``  the quarter's 10-Q or 10-K was public, without this metric;
6. ``not_yet_filed`` the quarter ended but its report was not public at the cutoff.

The mask is true for observed and derived cells only, and an empty cell is never zero.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.metrics import LineageMethod
from multiverse_contracts.normalized import FiscalPeriod
from multiverse_contracts.pit import (
    POINT_IN_TIME_VIEWS,
    CellState,
    KnowledgeView,
    PanelCell,
    PitValue,
)
from multiverse_pipelines.pit.clock import eastern_date
from multiverse_pipelines.pit.filings import Filing
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.cik import cik10
from multiverse_pipelines.xbrl.concepts import CALCULATED, METRICS

PANEL_METRICS = tuple(spec.metric for spec in METRICS) + tuple(spec.metric for spec in CALCULATED)
QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))
CellKey = tuple[str, str, str]
# The longest regular deadline (a 10-K of a non-accelerated filer).
OVERDUE = timedelta(days=90)


class LeakageError(RuntimeError):
    """A panel would contain something that was not public at its cutoff."""


def nearest_quarter_end(day: date) -> date:
    ends = [date(y, m, d) for y in (day.year - 1, day.year, day.year + 1) for m, d in QUARTER_ENDS]
    return min(ends, key=lambda end: (abs((end - day).days), end))


def _next_quarter_end(day: date) -> date:
    """The first calendar quarter end after a day."""
    return min(end for end in quarter_ends(date(day.year + 1, 3, 31), 6) if end > day)


def quarter_label(end: date) -> str:
    return f"{end.year}Q{end.month // 3}"


def quarter_ends(cutoff_day: date, count: int) -> list[date]:
    """The last ``count`` calendar quarter ends on or before a day, newest first."""
    year, number = cutoff_day.year, (cutoff_day.month - 1) // 3 + 1
    found: list[date] = []
    while len(found) < count:
        month, day = QUARTER_ENDS[number - 1]
        end = date(year, month, day)
        if end <= cutoff_day:
            found.append(end)
        number -= 1
        if number == 0:
            year, number = year - 1, 4
    return found


@dataclass(frozen=True)
class Panel:
    cutoff: datetime
    view: KnowledgeView
    cells: tuple[PanelCell, ...]
    sources: dict[CellKey, PitValue]
    """The value behind each masked cell, with its source facts and their timings."""


def _cell(
    cik: str,
    end: date,
    lag: int,
    metric: str,
    item: PitValue | None,
    gone: Filing | None,
    reported: bool,
    first_xbrl: date | None,
) -> PanelCell:
    base: dict[str, object] = {
        "cik": cik,
        "calendar_quarter": quarter_label(end),
        "quarter_end": end,
        "lag": lag,
        "metric": metric,
        "mask": False,
    }
    if gone is not None:
        return PanelCell.model_validate(
            {
                **base,
                "state": CellState.INACTIVE,
                "reason": f"{gone.form} filed on {gone.filing_date}; no report followed it",
            }
        )
    if item is not None:
        row = item.value
        details: dict[str, object] = {
            "fiscal_year": row.fiscal_year,
            "fiscal_period": row.fiscal_period,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "unit": row.unit,
            "currency": row.currency,
            "concept": row.concept,
            "flags": row.flags,
        }
        if row.value is not None:
            reported_value = row.method is LineageMethod.REPORTED
            return PanelCell.model_validate(
                {
                    **base,
                    **details,
                    "state": CellState.OBSERVED if reported_value else CellState.DERIVED,
                    "mask": True,
                    "value": row.value,
                    "method": row.method,
                    "accession": row.accession,
                    "known_from": item.known_from,
                }
            )
        if row.quality is QualitySeverity.BLOCKING:
            return PanelCell.model_validate(
                {**base, **details, "state": CellState.BLOCKED, "reason": row.missing_reason}
            )
        if reported:
            return PanelCell.model_validate(
                {**base, **details, "state": CellState.NOT_REPORTED, "reason": row.missing_reason}
            )
        return PanelCell.model_validate(
            {
                **base,
                **details,
                "state": CellState.NOT_YET_FILED,
                "reason": "the quarter's 10-Q or 10-K was not public at the cutoff",
            }
        )
    if first_xbrl is None or end < first_xbrl:
        reason = (
            "no XBRL report public at the cutoff"
            if first_xbrl is None
            else f"before the first XBRL report ({quarter_label(first_xbrl)})"
        )
        return PanelCell.model_validate({**base, "state": CellState.NOT_COVERED, "reason": reason})
    if reported:
        return PanelCell.model_validate(
            {
                **base,
                "state": CellState.NOT_REPORTED,
                "reason": "the report is public, but its facts place no value in this quarter",
            }
        )
    return PanelCell.model_validate(
        {
            **base,
            "state": CellState.NOT_YET_FILED,
            "reason": "the quarter's 10-Q or 10-K was not public at the cutoff",
        }
    )


def build_panel(
    warehouse: Warehouse,
    ciks: Iterable[str],
    cutoff: datetime,
    *,
    view: KnowledgeView = KnowledgeView.VINTAGE,
    quarters: int = 20,
    metrics: Sequence[str] = PANEL_METRICS,
) -> Panel:
    if view not in POINT_IN_TIME_VIEWS:
        raise ValueError("a panel is point-in-time: use the original or the vintage view")
    day = eastern_date(cutoff)
    ends = quarter_ends(day, quarters)
    cells: list[PanelCell] = []
    sources: dict[CellKey, PitValue] = {}
    for cik in sorted({cik10(c) for c in ciks}):
        index = warehouse.filings(cik)
        reports = index.reports(cutoff)
        reported = {nearest_quarter_end(f.report_date) for f in reports if f.report_date}
        first_xbrl = min(
            (nearest_quarter_end(f.report_date) for f in reports if f.xbrl and f.report_date),
            default=None,
        )
        rows: dict[tuple[str, date], PitValue] = {}
        for item in warehouse.as_of(cik, cutoff, view=view):
            if item.value.fiscal_period is FiscalPeriod.FY:
                continue
            slot = (item.value.metric, nearest_quarter_end(item.value.period_end))
            known = rows.get(slot)
            if known is None or item.value.period_end > known.value.period_end:
                rows[slot] = item
        if not rows:
            # Without an XBRL 10-K there is no fiscal calendar to place any quarter.
            first_xbrl = None
        gone = index.deregistered(cutoff)
        # Deregistered for good once the first report after the Form 15 is overdue.
        since = eastern_date(gone.known_at) if gone is not None else None
        confirmed = since is not None and day > _next_quarter_end(since) + OVERDUE
        for lag, end in enumerate(ends):
            for metric in metrics:
                found = rows.get((metric, end))
                inactive = confirmed and since is not None and end > since
                cell = _cell(
                    cik,
                    end,
                    lag,
                    metric,
                    found,
                    gone if inactive else None,
                    end in reported,
                    first_xbrl,
                )
                cells.append(cell)
                if cell.mask and found is not None:
                    sources[(cik, cell.calendar_quarter, metric)] = found
    panel = Panel(cutoff, view, tuple(cells), sources)
    check_point_in_time(panel)
    return panel


def check_point_in_time(panel: Panel) -> None:
    """Refuse a panel holding anything that was not public at its cutoff."""
    day = eastern_date(panel.cutoff)
    for cell in panel.cells:
        where = f"{cell.cik} {cell.calendar_quarter} {cell.metric}"
        if cell.quarter_end > day:
            raise LeakageError(f"{where}: the quarter ends after the cutoff")
        if not cell.mask:
            continue
        item = panel.sources[(cell.cik, cell.calendar_quarter, cell.metric)]
        if cell.known_from is None or cell.known_from > panel.cutoff:
            raise LeakageError(f"{where}: known only from {cell.known_from}")
        if cell.period_end is None or cell.period_end > day:
            raise LeakageError(f"{where}: the period ends after the cutoff")
        late = [t for t in item.timings if t.known_at > panel.cutoff]
        if late:
            raise LeakageError(f"{where}: source {late[0].accession} public at {late[0].known_at}")
