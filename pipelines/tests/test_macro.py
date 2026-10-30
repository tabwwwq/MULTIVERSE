"""Macro vintages and the as-of join (Stage 13). Every value here is synthetic.

The documents have the shape of ALFRED, ECB and World Bank responses, so the parsers,
the store and the join run exactly as they will on archived downloads.
"""

import json
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from multiverse_config import Settings
from multiverse_contracts.macro import (
    AvailabilityBasis,
    MacroCell,
    MacroCellState,
    MacroInput,
    MacroObservation,
    Transform,
)
from multiverse_contracts.pit import CellState, PanelCell
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_contracts.sources import DecisionStatus, DownloadDecision, DownloadScope
from multiverse_pipelines.macro import availability, cli, parsers, synthetic
from multiverse_pipelines.macro.fetch import (
    MissingKeyError,
    fetch_source,
    redact,
    require_macro_permission,
    unavailable_reason,
)
from multiverse_pipelines.macro.join import (
    check_macro_point_in_time,
    macro_join,
    months_in,
    windows,
)
from multiverse_pipelines.macro.qa import series_qa
from multiverse_pipelines.macro.registry import BY_ID, SERIES
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.clock import day_end, parse_cutoff
from multiverse_pipelines.pit.panel import LeakageError, quarter_ends, quarter_label
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.errors import PermissionRefusedError

CIK = "0000000021"
BUILT = datetime(2026, 10, 30, tzinfo=UTC)
UNTIL = date(2026, 10, 28)
SOURCES = {s.source_id: s for s in SOURCE_CATALOG.sources}


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def store_until(until: date) -> MacroStore:
    """The synthetic store as an archive downloaded on ``until`` would hold it."""
    return cli.load_synthetic(None, until, BUILT)


@pytest.fixture(scope="module")
def full() -> Iterator[MacroStore]:
    store = store_until(UNTIL)
    yield store
    store.close()


def panel(
    cutoff: date, quarters: int = 4, fiscal: dict[str, tuple[date, date]] | None = None
) -> list[PanelCell]:
    """A company's empty panel cells; ``fiscal`` gives fiscal dates to some quarters."""
    cells = []
    for lag, end in enumerate(quarter_ends(cutoff, quarters)):
        label = quarter_label(end)
        dates = (fiscal or {}).get(label)
        cells.append(
            PanelCell(
                cik=CIK,
                calendar_quarter=label,
                quarter_end=end,
                lag=lag,
                metric="revenue",
                state=CellState.NOT_YET_FILED,
                mask=False,
                period_start=dates[0] if dates else None,
                period_end=dates[1] if dates else None,
                reason="synthetic company",
            )
        )
    return cells


def join(
    store: MacroStore, cutoff: str, *, quarters: int = 4, **kwargs: Any
) -> dict[tuple[str, str], MacroCell]:
    moment = parse_cutoff(cutoff)
    cells = macro_join(
        panel(moment.date() if "T" in cutoff else date.fromisoformat(cutoff), quarters, **kwargs),
        store,
        SERIES,
        moment,
        unavailable={},
    )
    return {(c.calendar_quarter, c.feature): c for c in cells}


# ------------------------------------------------------------------ clocks


def test_central_european_time_and_target_days() -> None:
    assert availability.from_cet(datetime(2021, 3, 27, 16)) == utc(2021, 3, 27, 15)
    assert availability.from_cet(datetime(2021, 3, 29, 16)) == utc(2021, 3, 29, 14)
    assert availability.from_cet(datetime(2021, 10, 31, 16)) == utc(2021, 10, 31, 15)
    assert availability.easter(2024) == date(2024, 3, 31)
    assert availability.easter(2025) == date(2025, 4, 20)
    # Thursday before Easter: Good Friday and Easter Monday are TARGET holidays.
    assert availability.next_target_day(date(2025, 4, 17)) == date(2025, 4, 22)
    assert availability.next_target_day(date(2021, 12, 24)) == date(2021, 12, 27)
    assert availability.ecb_reference_rate(date(2021, 7, 1)) == utc(2021, 7, 1, 14)
    assert availability.ecb_yield_curve(date(2021, 12, 31)) == utc(2022, 1, 3, 11)
    with pytest.raises(ValueError, match="1996"):
        availability.from_cet(datetime(1995, 1, 1))


# ------------------------------------------------------------------ parsers


GDP = {
    "observations": [
        {
            "realtime_start": "2022-01-27",
            "realtime_end": "2022-02-23",
            "date": "2021-10-01",
            "value": "100.0",
        },
        {
            "realtime_start": "2022-02-24",
            "realtime_end": "2022-03-29",
            "date": "2021-10-01",
            "value": "101.5",
        },
        {
            "realtime_start": "2022-03-30",
            "realtime_end": "9999-12-31",
            "date": "2021-10-01",
            "value": "101.9",
        },
        {
            "realtime_start": "2021-01-28",
            "realtime_end": "9999-12-31",
            "date": "2020-10-01",
            "value": ".",
        },
    ]
}


def test_alfred_rows_become_availability_intervals() -> None:
    rows = parsers.alfred_observations("GDPC1", GDP)
    first, second, third, missing = rows
    assert first.available_from == day_end(date(2022, 1, 27))
    assert first.available_to == second.available_from == day_end(date(2022, 2, 24))
    assert third.available_to is None
    assert (first.period_start, first.period_end) == (date(2021, 10, 1), date(2021, 12, 31))
    assert missing.value is None
    assert {r.basis for r in rows} == {AvailabilityBasis.VINTAGE}
    with pytest.raises(parsers.UnknownSeriesError):
        parsers.alfred_observations("NOPE", GDP)


def test_a_later_revision_never_reaches_an_earlier_cutoff() -> None:
    store = MacroStore.create(None, synthetic=True, built_at=BUILT)
    store.add(parsers.alfred_observations("GDPC1", GDP))
    seen = {
        when: store.as_of("fred:GDPC1", parse_cutoff(when)).get(date(2021, 10, 1))
        for when in ("2022-01-26", "2022-02-01", "2022-03-01", "2022-04-01")
    }
    assert seen["2022-01-26"] is None
    assert [seen[w].value for w in ("2022-02-01", "2022-03-01", "2022-04-01")] == [
        "100.0",  # kept as published
        "101.5",
        "101.9",
    ]


def test_ecb_csv_and_world_bank_snapshots() -> None:
    text = (
        "KEY,FREQ,TIME_PERIOD,OBS_VALUE\n"
        "EXR.D.USD.EUR.SP00.A,D,2021-07-01,1.1884\n"
        "EXR.D.USD.EUR.SP00.A,D,2021-07-02,\n"  # a gap: no observation
    )
    (rate,) = parsers.ecb_observations(text)
    assert (rate.value, rate.basis, rate.available_from) == (
        "1.1884",
        AvailabilityBasis.SCHEDULE,
        utc(2021, 7, 1, 14),
    )

    def snapshot(updated: str, values: dict[int, float | None]) -> parsers.Snapshot:
        rows = [
            {
                "indicator": {"id": "FP.CPI.TOTL.ZG"},
                "countryiso3code": "USA",
                "date": str(y),
                "value": v,
            }
            for y, v in values.items()
        ]
        return parsers.worldbank_snapshot([{"lastupdated": updated}, rows])

    rows = parsers.worldbank_observations(
        [
            snapshot("2021-07-01", {2020: 1.2}),
            snapshot("2021-12-16", {2020: 1.25, 2021: None}),
            snapshot("2022-07-01", {2020: 1.25, 2021: 4.7}),
        ]
    )
    by_year = {(r.period_start.year, r.value): r for r in rows}
    assert by_year[(2020, "1.2")].available_to == day_end(date(2021, 12, 16))
    assert by_year[(2020, "1.25")].available_from == day_end(date(2021, 12, 16))
    assert by_year[(2021, "4.7")].available_from == day_end(date(2022, 7, 1))
    assert all(r.basis is AvailabilityBasis.SNAPSHOT for r in rows)


# ------------------------------------------------------------------ the join


def test_availability_not_the_observation_label_decides(full: MacroStore) -> None:
    december = date(2021, 12, 1)
    # Labelled December 2021, published in January 2022.
    assert december in full.first_available("fred:CPIAUCSL")
    assert december not in full.as_of("fred:CPIAUCSL", parse_cutoff("2021-12-31"))
    cells = join(full, "2021-12-31")
    cpi = cells[("2021Q4", "us_cpi_inflation")]
    assert (cpi.state, cpi.mask, cpi.value) == (MacroCellState.NOT_YET_RELEASED, False, None)
    assert cpi.reason == "2021-12-01 was not published by the cutoff"  # no later date
    later = join(full, "2022-01-13")
    assert later[("2021Q4", "us_cpi_inflation")].state is MacroCellState.OBSERVED
    assert cells[("2021Q3", "us_cpi_inflation")].state is MacroCellState.OBSERVED


def test_the_recession_flag_is_what_was_published_then(full: MacroStore) -> None:
    before = join(full, "2020-05-31", quarters=2)[("2020Q1", "us_recession")]
    after = join(full, "2020-06-30", quarters=2)[("2020Q1", "us_recession")]
    assert (before.value, after.value) == ("0", "1")  # today's series says 1 for both


def test_an_annual_value_never_reaches_a_quarter_before_its_release(full: MacroStore) -> None:
    spring = join(full, "2025-03-31")[("2024Q4", "wb_usa_inflation")]
    summer = join(full, "2025-07-02")[("2024Q4", "wb_usa_inflation")]
    assert [i.period_start.year for i in spring.inputs] == [2023]
    assert [i.period_start.year for i in summer.inputs] == [2024]
    early = join(full, "2009-03-31")[("2009Q1", "wb_usa_inflation")]
    assert early.state is MacroCellState.UNUSABLE
    assert early.reason == "no archived snapshot at or before the cutoff contains a year up to 2009"


def test_transforms_and_a_53_week_fiscal_quarter(full: MacroStore) -> None:
    fiscal = {"2020Q4": (date(2020, 9, 27), date(2021, 1, 2))}
    cells = join(full, "2021-03-31", quarters=3, fiscal=fiscal)
    rate = cells[("2020Q4", "us_policy_rate")]
    assert [i.period_start for i in rate.inputs] == [
        date(2020, 10, 1),
        date(2020, 11, 1),
        date(2020, 12, 1),
    ]
    mean = sum(Decimal(i.value) for i in rate.inputs) / 3
    assert Decimal(rate.value or "0") == mean.quantize(Decimal("0.000001")).normalize()
    eop = cells[("2020Q4", "eurusd")]
    assert eop.inputs[0].period_start <= date(2021, 1, 2)
    assert (eop.window_start, eop.window_end) == fiscal["2020Q4"]
    growth = cells[("2020Q4", "us_real_gdp_growth")]
    assert [i.period_start for i in growth.inputs] == [date(2019, 10, 1), date(2020, 10, 1)]
    assert months_in((date(2020, 9, 27), date(2021, 1, 2))) == [
        date(2020, 10, 1),
        date(2020, 11, 1),
        date(2020, 12, 1),
    ]


@pytest.mark.parametrize(
    "cutoff", ["2009-06-30", "2015-12-31", "2020-05-31", "2021-12-31", "2024-08-15"]
)
def test_later_publications_never_change_an_earlier_join(full: MacroStore, cutoff: str) -> None:
    then = store_until(date.fromisoformat(cutoff))
    assert join(full, cutoff, quarters=6) == join(then, cutoff, quarters=6)
    then.close()


def test_a_join_with_an_input_from_after_the_cutoff_is_refused() -> None:
    cell = MacroCell(
        cik=CIK,
        calendar_quarter="2021Q4",
        lag=0,
        window_start=date(2021, 10, 1),
        window_end=date(2021, 12, 31),
        feature="us_policy_rate",
        series_id="fred:FEDFUNDS",
        transform=Transform.QUARTER_MEAN,
        state=MacroCellState.OBSERVED,
        mask=True,
        value="1",
        inputs=(
            MacroInput(
                period_start=date(2021, 12, 1),
                period_end=date(2021, 12, 31),
                value="1",
                available_from=day_end(date(2022, 1, 3)),
                basis=AvailabilityBasis.VINTAGE,
            ),
        ),
    )
    with pytest.raises(LeakageError, match="published"):
        check_macro_point_in_time([cell], parse_cutoff("2021-12-31"))


def test_windows_prefer_fiscal_dates() -> None:
    cells = panel(date(2021, 3, 31), 2, fiscal={"2020Q4": (date(2020, 9, 27), date(2021, 1, 2))})
    found = windows(cells)
    assert found[(CIK, "2020Q4")] == (1, (date(2020, 9, 27), date(2021, 1, 2)))
    assert found[(CIK, "2021Q1")] == (0, (date(2021, 1, 1), date(2021, 3, 31)))


# ------------------------------------------------------------------ keys and degradation


def settings(**values: Any) -> Settings:
    return Settings.model_validate({"allow_network_downloads": True, **values})


def approved(source_id: str) -> Any:
    decision = DownloadDecision(
        status=DecisionStatus.APPROVED,
        decided_on=date(2026, 10, 30),
        scope=DownloadScope.SAMPLE,
        note="test",
    )
    return SOURCES[source_id].model_copy(update={"download": decision})


def test_missing_key_refuses_fred_before_any_request(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    transport = httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(500))
    archive = RawArchive(tmp_path, budget_bytes=1_000_000, source_dir="fred")
    with pytest.raises(MissingKeyError, match="MULTIVERSE_FRED_API_KEY"):
        fetch_source(
            settings(),
            approved("fred-alfred"),
            archive,
            run_id="t",
            catalog_version="t",
            transport=transport,
        )
    with pytest.raises(PermissionRefusedError, match="not approved"):
        require_macro_permission(settings(fred_api_key="k"), SOURCES["fred-alfred"])
    with pytest.raises(PermissionRefusedError, match="Network downloads are off"):
        require_macro_permission(settings(allow_network_downloads=False), approved("world-bank"))
    assert calls == []
    assert "D-11" in unavailable_reason(settings(), SOURCES["fred-alfred"])
    assert "D-12" in unavailable_reason(settings(), SOURCES["ecb-data-portal"])


def test_fred_key_is_used_but_never_stored(tmp_path: Path) -> None:
    fake = "x" * 32  # built at run time: no key-like literal in the repository
    doc = synthetic.fred_documents(date(2009, 3, 1))["FEDFUNDS"]

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_key"] == fake
        if request.url.path.endswith("/series"):
            notes = (
                "Copyright, 2016, Someone."
                if request.url.params["series_id"] == "T10Y2Y"
                else "Public domain."
            )
            return httpx.Response(
                200, stream=httpx.ByteStream(json.dumps({"seriess": [{"notes": notes}]}).encode())
            )
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(doc).encode()))

    archive = RawArchive(tmp_path, budget_bytes=5_000_000, source_dir="fred")
    report = fetch_source(
        settings(fred_api_key=fake),
        approved("fred-alfred"),
        archive,
        run_id="t",
        catalog_version="t",
        transport=httpx.MockTransport(respond),
        series_ids=["fred:FEDFUNDS", "fred:T10Y2Y"],
    )
    assert len(report.stored) == 1
    assert report.skipped == ["fred:T10Y2Y: notes mention copyright"]
    index = archive.index_path.read_text(encoding="utf-8")
    assert fake not in index
    assert "api_key=REDACTED" in index
    assert redact(f"https://x/y?a=1&api_key={fake}") == "https://x/y?a=1&api_key=REDACTED"


def test_without_data_every_cell_says_why() -> None:
    empty = MacroStore.create(None, synthetic=False, built_at=BUILT)
    reasons = {
        sid: unavailable_reason(settings(), SOURCES[sid])
        for sid in ("fred-alfred", "ecb-data-portal", "world-bank")
    }
    cells = macro_join(
        panel(date(2021, 12, 31), 2), empty, SERIES, parse_cutoff("2021-12-31"), unavailable=reasons
    )
    assert {c.state for c in cells} == {MacroCellState.UNAVAILABLE}
    fred = next(c for c in cells if c.series_id == "fred:FEDFUNDS")
    assert fred.reason
    assert "MULTIVERSE_FRED_API_KEY" in fred.reason


# ------------------------------------------------------------------ QA and commands


def test_qa_finds_impossible_timestamps_and_gaps() -> None:
    store = MacroStore.create(None, synthetic=True, built_at=BUILT)

    def obs(month: int, published: datetime, value: str | None = "1") -> MacroObservation:
        start = date(2021, month, 1)
        return MacroObservation(
            series_id="fred:UNRATE",
            period_start=start,
            period_end=parsers.period_end(start, BY_ID["fred:UNRATE"].frequency),
            value=value,
            available_from=published,
            basis=AvailabilityBasis.VINTAGE,
        )

    store.add(
        [
            obs(1, day_end(date(2021, 1, 20))),
            obs(2, day_end(date(2021, 3, 5)), None),
            obs(4, day_end(date(2021, 5, 7))),
        ]
    )
    (qa,) = series_qa(store, [BY_ID["fred:UNRATE"]])
    assert qa.problems == {"published_before_period_end": 1, "missing_value": 1, "gap": 1}
    assert qa.lag_days == [-11, 5, 7]


def test_the_commands_run_without_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in [n for n in os.environ if n.startswith("MULTIVERSE_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["status"]) == 0
    assert "key not set" in capsys.readouterr().out
    assert cli.main(["build"]) == 0
    assert cli.main(["fetch", "--source", "worldbank"]) == 2
    assert "Network downloads are off" in capsys.readouterr().err
    assert cli.main(["load-synthetic", "--until", "2012-06-30"]) == 0
    assert cli.main(["qa", "--synthetic"]) == 0
    qa = Path("var/data/macro/qa-synthetic/qa.md").read_text(encoding="utf-8")
    assert "SYNTHETIC" in qa
    assert cli.main(["as-of", "--synthetic", "--series", "fred:UNRATE", "--at", "2012-01-01"]) == 0
    assert "2011-11-01" in capsys.readouterr().out
    assert cli.main(["join", "--synthetic", "--cutoff", "2012-06-30"]) == 2  # no PIT warehouse here
    assert cli.main(["as-of", "--series", "fred:UNRATE", "--at", "2012-01-01"]) == 0
    assert cli.main(["as-of", "--synthetic", "--series", "fred:NOPE", "--at", "2012-01-01"]) == 2


def test_every_registered_series_has_its_rules() -> None:
    assert len(SERIES) == 18
    assert {s.source_id for s in SERIES} == {"fred-alfred", "ecb-data-portal", "world-bank"}
    assert len({s.feature for s in SERIES}) == 18
    for series in SERIES:
        assert series.publication_lag
        assert series.revision_cadence
        assert series.business_days
    assert timedelta(0) < availability.ecb_yield_curve(
        date(2021, 6, 30)
    ) - availability.ecb_reference_rate(date(2021, 6, 30))
