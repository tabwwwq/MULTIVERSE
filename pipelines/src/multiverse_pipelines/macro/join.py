"""The as-of join of macro features with company quarters (Stage 13, ADR-0020).

For every company quarter of a point-in-time panel (Stage 12) and every registered
series, one cell: the series' feature over the company's own fiscal quarter (calendar
quarter when the fiscal dates are not known), made only of observations available at
the cutoff, from one vintage. What decides is when a value was published, never the
period it is labelled with: at 31 December 2021, December's CPI does not exist yet.

States: ``observed``; ``not_yet_released`` (an input was published after the cutoff);
``unavailable`` (the source is not in the store: no key, no owner decision, nothing
downloaded); ``not_covered`` (before the series starts); ``unusable`` (inputs exist, but
their first publication is not evidenced at the cutoff, e.g. a World Bank year seen
only in a later snapshot).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from multiverse_contracts.macro import (
    EVIDENCED,
    MacroCell,
    MacroCellState,
    MacroInput,
    MacroObservation,
    MacroSeries,
    Transform,
    VintageSupport,
)
from multiverse_contracts.pit import PanelCell
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.clock import eastern_date
from multiverse_pipelines.pit.panel import LeakageError
from multiverse_pipelines.xbrl.normalize import decimal_text

FRACTION = Decimal("0.000001")
EOP_DAYS = 10
Window = tuple[date, date]
Series = dict[date, MacroObservation]


@dataclass(frozen=True)
class Outcome:
    state: MacroCellState
    value: Decimal | None = None
    inputs: tuple[MacroObservation, ...] = ()
    reason: str | None = None


def _text(value: Decimal) -> str:
    return decimal_text(value.quantize(FRACTION).normalize())


def windows(cells: Sequence[PanelCell]) -> dict[tuple[str, str], tuple[int, Window]]:
    """Each company quarter's fiscal dates, from its duration cells; else the calendar quarter."""
    found: dict[tuple[str, str], tuple[int, Window]] = {}
    # Cells with fiscal dates sort first within each company quarter.
    for cell in sorted(cells, key=lambda c: (c.cik, c.calendar_quarter, c.period_start is None)):
        key = (cell.cik, cell.calendar_quarter)
        if key in found:
            continue
        if cell.period_start is not None and cell.period_end is not None:
            found[key] = (cell.lag, (cell.period_start, cell.period_end))
        else:
            found[key] = (cell.lag, _calendar(cell.quarter_end))
    return found


def _calendar(end: date) -> Window:
    first_month = end.month - 2
    return date(end.year, first_month, 1), end


def months_in(window: Window) -> list[date]:
    """Month starts whose 15th day falls in the window."""
    start, end = window
    month = date(start.year, start.month, 1)
    found: list[date] = []
    while month <= end:
        if start <= month.replace(day=15) <= end:
            found.append(month)
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return found


def _shift_months(month: date, delta: int) -> date:
    index = month.year * 12 + month.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


@dataclass(frozen=True)
class Context:
    """What a series offers at the cutoff, and nothing from after it."""

    current: Series
    """Each period's value valid at the cutoff."""
    known: Series
    """Each period's first publication at or before the cutoff."""
    support: VintageSupport


def _not_published(what: str, ctx: Context) -> Outcome:
    # Only the series' own rules are used here: a reason never tells what came later.
    if ctx.support is VintageSupport.ARCHIVE:
        return Outcome(
            MacroCellState.UNUSABLE,
            reason=f"no archived snapshot at or before the cutoff contains {what}",
        )
    return Outcome(
        MacroCellState.NOT_YET_RELEASED, reason=f"{what} was not published by the cutoff"
    )


def _missing(periods: Sequence[date], ctx: Context) -> Outcome | None:
    """Why some of the needed periods have no value at the cutoff, if any."""
    absent = [p for p in periods if p not in ctx.current or ctx.current[p].value is None]
    if not absent:
        return None
    period = absent[0]
    if ctx.known and period < min(ctx.known):
        return Outcome(MacroCellState.NOT_COVERED, reason=f"the series starts after {period}")
    if period in ctx.current:
        return Outcome(MacroCellState.UNUSABLE, reason=f"the source marks {period} missing")
    return _not_published(str(period), ctx)


def _value(observation: MacroObservation) -> Decimal:
    return Decimal(observation.value or "0")


def quarter_mean(window: Window, ctx: Context) -> Outcome:
    months = months_in(window)
    problem = _missing(months, ctx)
    if problem:
        return problem
    used = tuple(ctx.current[m] for m in months)
    return Outcome(MacroCellState.OBSERVED, sum(map(_value, used), Decimal(0)) / len(used), used)


def quarter_max(window: Window, ctx: Context) -> Outcome:
    months = months_in(window)
    problem = _missing(months, ctx)
    if problem:
        return problem
    used = tuple(ctx.current[m] for m in months)
    return Outcome(MacroCellState.OBSERVED, max(map(_value, used)), used)


def end_of_period(window: Window, ctx: Context) -> Outcome:
    end = window[1]
    earliest_day = end - timedelta(days=EOP_DAYS)
    current = ctx.current
    days = [d for d in current if earliest_day <= d <= end and current[d].value is not None]
    if days:
        used = current[max(days)]
        return Outcome(MacroCellState.OBSERVED, _value(used), (used,))
    if ctx.known and end < min(ctx.known):
        return Outcome(MacroCellState.NOT_COVERED, reason=f"the series starts after {end}")
    return _not_published(f"a value in the {EOP_DAYS} days before {end}", ctx)


def yoy_last_month(window: Window, ctx: Context) -> Outcome:
    months = months_in(window)
    if not months:
        return Outcome(MacroCellState.NOT_COVERED, reason="no month falls in the quarter")
    last, base = months[-1], _shift_months(months[-1], -12)
    problem = _missing([last, base], ctx)
    if problem:
        return problem
    now, before = ctx.current[last], ctx.current[base]
    return Outcome(MacroCellState.OBSERVED, (_value(now) / _value(before) - 1) * 100, (before, now))


def yoy_quarter(window: Window, ctx: Context) -> Outcome:
    middle = window[0] + (window[1] - window[0]) / 2
    quarter = date(middle.year, 3 * ((middle.month - 1) // 3) + 1, 1)
    base = date(quarter.year - 1, quarter.month, 1)
    problem = _missing([quarter, base], ctx)
    if problem:
        return problem
    now, before = ctx.current[quarter], ctx.current[base]
    return Outcome(MacroCellState.OBSERVED, (_value(now) / _value(before) - 1) * 100, (before, now))


def latest_year(window: Window, ctx: Context) -> Outcome:
    """The latest year available at the cutoff, never after the quarter's year."""
    current = ctx.current
    years = sorted(
        (p for p in current if current[p].period_end <= window[1] and current[p].value is not None),
        reverse=True,
    )
    if years:
        used = current[years[0]]
        return Outcome(MacroCellState.OBSERVED, _value(used), (used,))
    if ctx.known and window[1] < min(ctx.known):
        return Outcome(
            MacroCellState.NOT_COVERED, reason="the series has no year up to this quarter"
        )
    return _not_published(f"a year up to {window[1].year}", ctx)


TRANSFORMS: dict[Transform, Callable[[Window, Context], Outcome]] = {
    Transform.QUARTER_MEAN: quarter_mean,
    Transform.QUARTER_MAX: quarter_max,
    Transform.END_OF_PERIOD: end_of_period,
    Transform.YOY_LAST_MONTH: yoy_last_month,
    Transform.YOY_QUARTER: yoy_quarter,
    Transform.LATEST_YEAR: latest_year,
}


def macro_join(
    cells: Sequence[PanelCell],
    store: MacroStore,
    series: Sequence[MacroSeries],
    cutoff: datetime,
    *,
    unavailable: Mapping[str, str],
) -> list[MacroCell]:
    """``unavailable`` maps a source id to why it is not in the store (key, decision)."""
    stored = set(store.series())
    found: list[MacroCell] = []
    company_quarters = windows(cells)
    for item in series:
        present = item.series_id in stored
        ctx = Context(
            store.as_of(item.series_id, cutoff) if present else {},
            store.first_available(item.series_id, until=cutoff) if present else {},
            item.vintage_support,
        )
        for (cik, quarter), (lag, window) in sorted(company_quarters.items()):
            if not present:
                outcome = Outcome(
                    MacroCellState.UNAVAILABLE,
                    reason=unavailable.get(item.source_id, f"{item.series_id} is not in the store"),
                )
            else:
                outcome = TRANSFORMS[item.transform](window, ctx)
            found.append(_cell(cik, quarter, lag, window, item, outcome, store.synthetic))
    check_macro_point_in_time(found, cutoff)
    return found


def _cell(
    cik: str,
    quarter: str,
    lag: int,
    window: Window,
    series: MacroSeries,
    outcome: Outcome,
    synthetic: bool,
) -> MacroCell:
    state, reason = outcome.state, outcome.reason
    if state is MacroCellState.OBSERVED and any(o.basis not in EVIDENCED for o in outcome.inputs):
        state, reason = (
            MacroCellState.UNUSABLE,
            "the first publication of an input is not evidenced",
        )
    observed = state is MacroCellState.OBSERVED
    return MacroCell(
        cik=cik,
        calendar_quarter=quarter,
        lag=lag,
        window_start=window[0],
        window_end=window[1],
        feature=series.feature,
        series_id=series.series_id,
        transform=series.transform,
        state=state,
        mask=observed,
        value=_text(outcome.value) if observed and outcome.value is not None else None,
        inputs=tuple(
            MacroInput(
                period_start=o.period_start,
                period_end=o.period_end,
                value=o.value or "0",
                available_from=o.available_from,
                basis=o.basis,
                raw_sha256=o.raw_sha256,
            )
            for o in outcome.inputs
        )
        if observed
        else (),
        synthetic=synthetic or any(o.synthetic for o in outcome.inputs),
        reason=None if observed else reason or "no value at the cutoff",
    )


def check_macro_point_in_time(cells: Sequence[MacroCell], cutoff: datetime) -> None:
    """Refuse a join holding a value published, or a period ending, after the cutoff."""
    day = eastern_date(cutoff)
    for cell in cells:
        for item in cell.inputs:
            where = f"{cell.cik} {cell.calendar_quarter} {cell.feature}"
            if item.available_from > cutoff:
                raise LeakageError(
                    f"{where}: input {item.period_start} published {item.available_from}"
                )
            if item.period_end > day:
                raise LeakageError(f"{where}: input period ends {item.period_end}")
