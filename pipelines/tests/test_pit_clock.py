"""EDGAR's clock, calendar quarters and panel features (Stage 12)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from multiverse_contracts.metrics import LineageMethod
from multiverse_contracts.pit import CellState, PanelCell, TimePrecision
from multiverse_pipelines.pit.clock import (
    EDT,
    EST,
    day_end,
    day_start,
    daylight_saving,
    eastern_date,
    from_stamp,
    knowledge_time,
    offset_at,
    parse_cutoff,
    stamp,
    to_eastern,
)
from multiverse_pipelines.pit.features import trailing_twelve_months, year_over_year
from multiverse_pipelines.pit.filings import FilingIndex, filings_from_tables
from multiverse_pipelines.pit.panel import nearest_quarter_end, quarter_ends, quarter_label


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


@pytest.mark.parametrize(
    ("moment", "offset"),
    [
        (utc(2021, 3, 14, 6, 59), EST),  # 1:59 a.m. EST, the night daylight saving starts
        (utc(2021, 3, 14, 7, 0), EDT),  # 3:00 a.m. EDT
        (utc(2021, 11, 7, 5, 59), EDT),  # 1:59 a.m. EDT, the night it ends
        (utc(2021, 11, 7, 6, 0), EST),  # 1:00 a.m. EST
        (utc(2005, 4, 3, 7, 0), EDT),  # first Sunday of April before 2007
        (utc(2005, 10, 30, 6, 0), EST),  # last Sunday of October before 2007
        (utc(2005, 3, 13, 12, 0), EST),  # the 2007 rule did not apply yet
    ],
)
def test_the_eastern_offset_follows_us_daylight_saving(moment: datetime, offset: timedelta) -> None:
    assert offset_at(moment) == offset


def test_eastern_days_and_their_bounds() -> None:
    assert day_end(date(2021, 12, 31)) == datetime(2022, 1, 1, 4, 59, 59, 999999, tzinfo=UTC)
    assert day_end(date(2021, 7, 1)) == datetime(2021, 7, 2, 3, 59, 59, 999999, tzinfo=UTC)
    assert day_start(date(2022, 1, 3)) == utc(2022, 1, 3, 5)
    assert eastern_date(utc(2022, 1, 1, 3, 0)) == date(2021, 12, 31)
    assert to_eastern(utc(2021, 2, 11, 21, 30)) == datetime(2021, 2, 11, 16, 30)
    with pytest.raises(ValueError, match="1987"):
        daylight_saving(1986)
    with pytest.raises(ValueError, match="time zone"):
        to_eastern(datetime(2021, 1, 1))


def test_a_filing_is_public_from_acceptance_but_never_before_its_filing_date() -> None:
    during = utc(2021, 2, 11, 21, 30)  # 4:30 p.m. Eastern on its filing date
    assert knowledge_time(date(2021, 2, 11), during) == (during, TimePrecision.ACCEPTED)
    evening = utc(2021, 12, 31, 23, 10)  # 6:10 p.m. Eastern, dated the next business day
    assert knowledge_time(date(2022, 1, 3), evening) == (
        utc(2022, 1, 3, 5),
        TimePrecision.FILING_DAY_START,
    )
    midnight = utc(1998, 5, 14, 4)  # date only, as in 1990s filings
    assert knowledge_time(date(1998, 5, 14), midnight) == (
        day_end(date(1998, 5, 14)),
        TimePrecision.FILING_DAY_END,
    )
    assert knowledge_time(date(2020, 1, 2), None)[1] is TimePrecision.FILING_DAY_END
    late = utc(2021, 3, 1, 21)  # accepted four days after its filing date
    assert knowledge_time(date(2021, 2, 25), late) == (late, TimePrecision.ACCEPTED)


def test_cutoffs_are_dates_or_times_with_an_offset() -> None:
    assert parse_cutoff("2021-12-31") == day_end(date(2021, 12, 31))
    assert parse_cutoff("2021-12-31T16:00:00-05:00") == utc(2021, 12, 31, 21)
    assert parse_cutoff("2021-12-31T21:00:00Z") == utc(2021, 12, 31, 21)
    with pytest.raises(ValueError, match="offset"):
        parse_cutoff("2021-12-31T16:00:00")


def test_stamps_sort_like_the_moments_they_name() -> None:
    moments = [utc(2021, 1, 1, 0, 0, 0), utc(2020, 12, 31, 23, 59, 59), utc(2021, 1, 1, 0, 0, 1)]
    stamps = [stamp(m) for m in moments]
    assert sorted(stamps) == [stamp(m) for m in sorted(moments)]
    assert all(from_stamp(s) == m for s, m in zip(stamps, moments, strict=True))


def test_filings_index_and_deregistration() -> None:
    table = {
        "accessionNumber": ["0000000001-19-000001", "0000000001-19-000002", "0000000001-19-000003"],
        "form": ["10-Q", "15-12B", "10-Q"],
        "filingDate": ["2019-05-01", "2019-06-01", "2019-08-01"],
        "reportDate": ["2019-03-31", "", "2019-06-30"],
        "acceptanceDateTime": ["2019-05-01T20:00:00.000Z", "", "2019-08-01T20:00:00.000Z"],
        "isXBRL": [1, 0, 1],
    }
    index = FilingIndex(filings_from_tables([table]))
    # A Form 15 for one class of securities: a later 10-Q shows the company still reports.
    assert index.deregistered(day_end(date(2019, 7, 1))) is not None
    assert index.deregistered(day_end(date(2019, 8, 1))) is None
    fallback = index.timing("0000000001-19-000099", date(2019, 9, 3))
    assert fallback.precision is TimePrecision.FILING_DAY_END
    assert [f.report_date for f in index.reports(day_end(date(2019, 6, 1)))] == [date(2019, 3, 31)]


@pytest.mark.parametrize(
    ("day", "end"),
    [
        (date(2021, 1, 2), date(2020, 12, 31)),  # 52/53-week year ending early January
        (date(2021, 1, 31), date(2020, 12, 31)),  # retail year ending in January
        (date(2021, 2, 28), date(2021, 3, 31)),
        (date(2020, 3, 28), date(2020, 3, 31)),
        (date(2020, 9, 26), date(2020, 9, 30)),
    ],
)
def test_fiscal_quarters_belong_to_the_nearest_calendar_quarter(day: date, end: date) -> None:
    assert nearest_quarter_end(day) == end


def test_the_panel_window_counts_back_from_the_cutoff() -> None:
    assert quarter_ends(date(2021, 12, 31), 3) == [
        date(2021, 12, 31),
        date(2021, 9, 30),
        date(2021, 6, 30),
    ]
    assert quarter_ends(date(2021, 12, 30), 2) == [date(2021, 9, 30), date(2021, 6, 30)]
    assert quarter_label(date(2021, 9, 30)) == "2021Q3"


def _cell(lag: int, value: str | None) -> PanelCell:
    end = quarter_ends(date(2021, 12, 31), 8)[lag]
    if value is None:
        return PanelCell(
            cik="0000000001",
            calendar_quarter=quarter_label(end),
            quarter_end=end,
            lag=lag,
            metric="revenue",
            state=CellState.NOT_YET_FILED,
            mask=False,
            reason="not public at the cutoff",
        )
    return PanelCell(
        cik="0000000001",
        calendar_quarter=quarter_label(end),
        quarter_end=end,
        lag=lag,
        metric="revenue",
        state=CellState.OBSERVED,
        mask=True,
        value=value,
        period_end=end,
        method=LineageMethod.REPORTED,
        known_from=utc(2022, 1, 1),
    )


def test_features_propagate_the_mask_and_never_fill_with_zero() -> None:
    cells = [_cell(0, None)] + [_cell(lag, str(100 + lag)) for lag in range(1, 8)]
    ttm = {f.lag: f for f in trailing_twelve_months(cells, "revenue")}
    assert not ttm[0].mask
    assert ttm[0].value is None
    assert ttm[0].reason == "needs four masked quarters; missing 2021Q4"
    assert ttm[1].value == Decimal(101 + 102 + 103 + 104)
    assert not ttm[5].mask  # fewer than four quarters left in the window
    growth = {f.lag: f for f in year_over_year(cells, "revenue")}
    assert growth[1].value == (Decimal(101) / Decimal(105) - 1).quantize(Decimal("0.000001"))
    assert not growth[0].mask
    assert not growth[4].mask
