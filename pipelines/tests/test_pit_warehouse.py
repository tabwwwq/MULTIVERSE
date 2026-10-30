"""Point-in-time warehouse on adversarial synthetic companies (Stage 12).

Every company, accession, date and value here is invented. The files have the shape of
SEC Company Facts and submissions, so the same code runs on the archived sample.

- Alpha: calendar year; Q4 2020 public only in 2021; a 10-K/A restates 2020 revenue;
  cash flow reported only year to date; no R&D at all; a quarterly amendment accepted
  on the evening of 31 December 2021 and dated 3 January 2022; an estimate for a future
  year inside a 10-K; a fact whose filing is missing from the index.
- Beta: deregisters (Form 25, then Form 15) after its third 2019 quarter; one 10-Q
  filed late and out of order, one amendment public before the report it amends.
- Gamma: 52/53-week fiscal year; fiscal 2020 has 53 weeks and ends 2 January 2021.
"""

import json
import os
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.metrics import LineageMethod
from multiverse_contracts.normalized import FiscalPeriod, QualityFlag
from multiverse_contracts.pit import (
    AlertKind,
    CellState,
    EntityAttribute,
    EntityAttributeName,
    KnowledgeView,
    PitSnapshotManifest,
    ValueChange,
)
from multiverse_pipelines.pit import cli
from multiverse_pipelines.pit.build import CompanyInputs, prepare
from multiverse_pipelines.pit.clock import day_end, eastern_date, parse_cutoff
from multiverse_pipelines.pit.features import build_features
from multiverse_pipelines.pit.filings import attribute_as_of, resolve_ticker
from multiverse_pipelines.pit.panel import LeakageError, Panel, build_panel, check_point_in_time
from multiverse_pipelines.pit.snapshot import lineage_rows, make_snapshot, write_snapshot
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.xbrl.facts import facts_from_companyfacts
from multiverse_pipelines.xbrl.normalize import CompanyNormalizer

ALPHA, BETA, GAMMA = "0000000011", "0000000012", "0000000013"
OBSERVED = datetime(2026, 10, 29, 19, 0, tzinfo=UTC)
BUILT = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


class Company:
    """A synthetic filer: its filing index and its XBRL facts."""

    def __init__(self, cik: str, name: str, *, tickers: tuple[str, ...] = ()) -> None:
        self.cik = cik
        self.name = name
        self.tickers = list(tickers)
        self.former: list[dict[str, str]] = []
        self.filings: list[dict[str, Any]] = []
        self.facts: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )

    def filing(
        self, number: int, form: str, filed: str, report: str | None, accepted: str | None
    ) -> str:
        accession = f"{self.cik}-{filed[2:4]}-{number:06d}"
        self.filings.append(
            {
                "accessionNumber": accession,
                "form": form,
                "filingDate": filed,
                "reportDate": report or "",
                "acceptanceDateTime": accepted or "",
                "isXBRL": int(form.startswith("10-")),
            }
        )
        return accession

    def fact(
        self,
        tag: str,
        value: int,
        period: tuple[str | None, str],
        accession: str,
        *,
        unit: str = "USD",
        fy: int | None = None,
        filed: str | None = None,
        form: str | None = None,
        taxonomy: str = "us-gaap",
    ) -> None:
        filing = next((f for f in self.filings if f["accessionNumber"] == accession), None)
        start, end = period
        record: dict[str, Any] = {
            "end": end,
            "val": value,
            "accn": accession,
            "fy": fy,
            "fp": None,
            "form": form or (filing["form"] if filing else "8-K"),
            "filed": filed or (filing["filingDate"] if filing else ""),
        }
        if start is not None:
            record["start"] = start
        self.facts[taxonomy][tag][unit].append(record)

    def companyfacts(self) -> dict[str, Any]:
        return {
            "cik": int(self.cik),
            "entityName": self.name,
            "facts": {
                taxonomy: {tag: {"units": dict(units)} for tag, units in tags.items()}
                for taxonomy, tags in self.facts.items()
            },
        }

    def submissions(self) -> dict[str, Any]:
        columns = ("accessionNumber", "form", "filingDate", "reportDate", "acceptanceDateTime")
        recent: dict[str, list[Any]] = {name: [f[name] for f in self.filings] for name in columns}
        recent["isXBRL"] = [f["isXBRL"] for f in self.filings]
        return {
            "cik": str(int(self.cik)),
            "name": self.name,
            "tickers": self.tickers,
            "exchanges": ["Nasdaq"] * len(self.tickers),
            "sic": "3674",
            "formerNames": self.former,
            "filings": {"recent": recent, "files": []},
        }

    def inputs(self) -> CompanyInputs:
        raw = RawObject(
            source_id="sec-edgar",
            dataset_id="sec-companyfacts",
            key=f"CIK{self.cik}",
            cik=self.cik,
            url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{self.cik}.json",
            path=f"sec/companyfacts/CIK{self.cik}/{'0' * 64}.json",
            sha256="0" * 64,
            size_bytes=1,
            file_format="json",
            content_encoding="identity",
            http_status=200,
            downloaded_at=OBSERVED,
            run_id="fixture",
            licence="fixture",
            terms_checked_on=date(2026, 10, 29),
            catalog_version="0.9.0",
        )
        return CompanyInputs(
            cik=self.cik,
            facts=facts_from_companyfacts(self.companyfacts()),
            submissions=self.submissions(),
            pages=[],
            observed_at=OBSERVED,
            files=[raw],
        )


def year(y: int) -> tuple[str, str]:
    return f"{y}-01-01", f"{y}-12-31"


def q(y: int, n: int) -> tuple[str, str]:
    starts = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}
    ends = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    return f"{y}-{starts[n]}", f"{y}-{ends[n]}"


def ytd(y: int, months: int) -> tuple[str, str]:
    return f"{y}-01-01", {6: f"{y}-06-30", 9: f"{y}-09-30"}[months]


def at(y: int, m: int, d: int) -> tuple[None, str]:
    return None, date(y, m, d).isoformat()


def alpha() -> Company:
    c = Company(ALPHA, "ALPHA CORP", tickers=("ALPX",))
    c.former = [
        {
            "name": "ALPHA HOLDINGS INC",
            "from": "2010-01-04T05:00:00.000Z",
            "to": "2020-06-01T04:00:00.000Z",
        }
    ]
    k19 = c.filing(1, "10-K", "2020-02-13", "2019-12-31", "2020-02-13T21:05:00.000Z")
    q120 = c.filing(2, "10-Q", "2020-04-30", "2020-03-31", "2020-04-30T20:10:00.000Z")
    q220 = c.filing(3, "10-Q", "2020-07-30", "2020-06-30", "2020-07-30T20:10:00.000Z")
    q320 = c.filing(4, "10-Q", "2020-10-29", "2020-09-30", "2020-10-29T20:10:00.000Z")
    k20 = c.filing(5, "10-K", "2021-02-11", "2020-12-31", "2021-02-11T21:30:00.000Z")
    ka20 = c.filing(6, "10-K/A", "2021-06-15", "2020-12-31", "2021-06-15T14:00:00.000Z")
    q121 = c.filing(7, "10-Q", "2021-04-29", "2021-03-31", "2021-04-29T20:10:00.000Z")
    q221 = c.filing(8, "10-Q", "2021-07-29", "2021-06-30", "2021-07-29T20:10:00.000Z")
    q321 = c.filing(9, "10-Q", "2021-10-28", "2021-09-30", "2021-10-28T20:10:00.000Z")
    # Accepted 6:10 p.m. Eastern on 31 December 2021: EDGAR dates it 3 January 2022.
    qa321 = c.filing(10, "10-Q/A", "2022-01-03", "2021-09-30", "2021-12-31T23:10:00.000Z")
    k21 = c.filing(11, "10-K", "2022-02-10", "2021-12-31", "2022-02-10T21:00:00.000Z")

    c.fact("Revenues", 1000, year(2019), k19, fy=2019)
    c.fact("Revenues", 900, year(2018), k19, fy=2019)
    c.fact("NetCashProvidedByUsedInOperatingActivities", 300, year(2019), k19, fy=2019)
    c.fact("CashAndCashEquivalentsAtCarryingValue", 50, at(2019, 12, 31), k19, fy=2019)
    c.fact("Revenues", 260, q(2020, 1), q120)
    c.fact("Revenues", 240, q(2019, 1), q120)
    c.fact("NetCashProvidedByUsedInOperatingActivities", 70, q(2020, 1), q120)
    c.fact("CashAndCashEquivalentsAtCarryingValue", 55, at(2020, 3, 31), q120)
    c.fact("Revenues", 270, q(2020, 2), q220)
    c.fact("Revenues", 530, ytd(2020, 6), q220)
    # Company Facts gives this filing a different date than the filing index.
    c.fact(
        "NetCashProvidedByUsedInOperatingActivities", 150, ytd(2020, 6), q220, filed="2020-07-31"
    )
    c.fact("Revenues", 280, q(2020, 3), q320)
    c.fact("Revenues", 810, ytd(2020, 9), q320)
    c.fact("NetCashProvidedByUsedInOperatingActivities", 240, ytd(2020, 9), q320)
    c.fact("Revenues", 1100, year(2020), k20, fy=2020)
    c.fact("Revenues", 1000, year(2019), k20, fy=2020)
    c.fact("NetCashProvidedByUsedInOperatingActivities", 340, year(2020), k20, fy=2020)
    c.fact("CashAndCashEquivalentsAtCarryingValue", 70, at(2020, 12, 31), k20, fy=2020)
    # An estimate for a year that has not happened yet, inside the 10-K.
    c.fact("Revenues", 1500, year(2021), k20, fy=2020)
    c.fact("Revenues", 1080, year(2020), ka20, fy=2020)
    c.fact("NetCashProvidedByUsedInOperatingActivities", 340, year(2020), ka20, fy=2020)
    c.fact("Revenues", 300, q(2021, 1), q121)
    c.fact("Revenues", 260, q(2020, 1), q121)
    c.fact("NetCashProvidedByUsedInOperatingActivities", 75, q(2021, 1), q121)
    c.fact("Revenues", 310, q(2021, 2), q221)
    c.fact("Revenues", 610, ytd(2021, 6), q221)
    c.fact("Revenues", 320, q(2021, 3), q321)
    c.fact("Revenues", 930, ytd(2021, 9), q321)
    c.fact("Revenues", 800, ytd(2020, 9), q321)
    c.fact("Revenues", 325, q(2021, 3), qa321)
    c.fact("Revenues", 935, ytd(2021, 9), qa321)
    c.fact("Revenues", 1260, year(2021), k21, fy=2021)
    c.fact("Revenues", 1080, year(2020), k21, fy=2021)
    c.fact("Revenues", 340, q(2021, 4), k21, fy=2021)
    # A filing that is not in the index: public from the end of its filing date.
    c.fact(
        "EntityPublicFloat",
        5000,
        at(2021, 6, 30),
        "0000000011-21-000099",
        filed="2021-08-02",
        form="8-K",
        taxonomy="dei",
    )
    return c


def beta() -> Company:
    c = Company(BETA, "BETA INC")
    k18 = c.filing(1, "10-K", "2019-02-20", "2018-12-31", "2019-02-20T21:00:00.000Z")
    qa219 = c.filing(2, "10-Q/A", "2019-08-01", "2019-06-30", "2019-08-01T14:00:00.000Z")
    q219 = c.filing(3, "10-Q", "2019-08-05", "2019-06-30", "2019-08-05T20:00:00.000Z")
    q119 = c.filing(4, "10-Q", "2019-08-10", "2019-03-31", "2019-08-10T16:00:00.000Z")
    q319 = c.filing(5, "10-Q", "2019-10-30", "2019-09-30", "2019-10-30T20:00:00.000Z")
    c.filing(6, "25-NSE", "2019-11-20", None, "2019-11-20T13:00:00.000Z")
    c.filing(7, "15-12B", "2019-12-13", None, "2019-12-13T15:00:00.000Z")
    c.fact("Revenues", 400, year(2018), k18, fy=2018)
    c.fact("Revenues", 380, year(2017), k18, fy=2018)
    c.fact("Revenues", 101, q(2019, 2), qa219)
    c.fact("Revenues", 100, q(2019, 1), q119)
    c.fact("Revenues", 102, q(2019, 2), q219)
    c.fact("Revenues", 103, q(2019, 3), q319)
    return c


def gamma() -> Company:
    c = Company(GAMMA, "GAMMA SYSTEMS")
    k19 = c.filing(1, "10-K", "2020-02-20", "2019-12-28", "2020-02-20T21:00:00.000Z")
    q120 = c.filing(2, "10-Q", "2020-05-07", "2020-03-28", "2020-05-07T20:00:00.000Z")
    q220 = c.filing(3, "10-Q", "2020-08-06", "2020-06-27", "2020-08-06T20:00:00.000Z")
    q320 = c.filing(4, "10-Q", "2020-11-05", "2020-09-26", "2020-11-05T21:00:00.000Z")
    # Dated 25 February, accepted four days later.
    k20 = c.filing(5, "10-K", "2021-02-25", "2021-01-02", "2021-03-01T21:00:00.000Z")
    c.fact("Revenues", 4000, ("2018-12-30", "2019-12-28"), k19, fy=2019)
    c.fact("Revenues", 3800, ("2017-12-31", "2018-12-29"), k19, fy=2019)
    c.fact("Revenues", 1000, ("2019-12-29", "2020-03-28"), q120)
    c.fact("Revenues", 1000, ("2020-03-29", "2020-06-27"), q220)
    c.fact("Revenues", 2000, ("2019-12-29", "2020-06-27"), q220)
    c.fact("Revenues", 1000, ("2020-06-28", "2020-09-26"), q320)
    c.fact("Revenues", 3000, ("2019-12-29", "2020-09-26"), q320)
    c.fact("Revenues", 4400, ("2019-12-29", "2021-01-02"), k20, fy=2020)
    c.fact("Revenues", 4000, ("2018-12-30", "2019-12-28"), k20, fy=2020)
    return c


def build(*companies: Company, known_by: datetime | None = None) -> Warehouse:
    warehouse = Warehouse.create(None, built_at=BUILT)
    for company in companies:
        item = prepare(company.inputs(), known_by)
        warehouse.add_company(item.history, item.filings, item.attributes, item.alerts, item.files)
    return warehouse


@pytest.fixture(scope="module")
def warehouse() -> Iterator[Warehouse]:
    built = build(alpha(), beta(), gamma())
    yield built
    built.close()


def values(
    warehouse: Warehouse,
    cik: str,
    when: datetime | str,
    metric: str = "revenue",
    view: KnowledgeView = KnowledgeView.VINTAGE,
) -> dict[tuple[int, FiscalPeriod], str | None]:
    moment = parse_cutoff(when) if isinstance(when, str) else when
    return {
        (v.value.fiscal_year, v.value.fiscal_period): v.value.value
        for v in warehouse.as_of(cik, moment, view=view, metric=metric)
    }


def cell(panel: Panel, cik: str, quarter: str, metric: str = "revenue") -> Any:
    return next(
        c
        for c in panel.cells
        if c.cik == cik and c.calendar_quarter == quarter and c.metric == metric
    )


# ------------------------------------------------------------------ the cutoff rule


def test_a_cutoff_never_sees_a_filing_dated_after_it(warehouse: Warehouse) -> None:
    cutoff = parse_cutoff("2021-12-31")
    panel = build_panel(warehouse, [ALPHA], cutoff, quarters=8)
    assert cell(panel, ALPHA, "2021Q3").value == "320"  # the 10-Q/A is dated 2022
    assert cell(panel, ALPHA, "2021Q4").state is CellState.NOT_YET_FILED
    for item in warehouse.as_of(ALPHA, cutoff):
        assert all(source.filed <= date(2021, 12, 31) for source in item.value.sources)
        assert all(timing.known_at <= cutoff for timing in item.timings)
    later = build_panel(warehouse, [ALPHA], parse_cutoff("2022-01-03"), quarters=8)
    assert cell(later, ALPHA, "2021Q3").value == "325"


def test_q4_is_public_only_with_the_next_year_10k(warehouse: Warehouse) -> None:
    for when in ("2020-12-31", "2021-02-11T16:29:59-05:00"):
        panel = build_panel(warehouse, [ALPHA], parse_cutoff(when), quarters=4)
        assert cell(panel, ALPHA, "2020Q4").state is CellState.NOT_YET_FILED
        assert values(warehouse, ALPHA, when)[(2020, FiscalPeriod.FY)] is None
    accepted = "2021-02-11T16:30:00-05:00"
    panel = build_panel(warehouse, [ALPHA], parse_cutoff(accepted), quarters=4)
    q4 = cell(panel, ALPHA, "2020Q4")
    assert (q4.state, q4.value, q4.method) == (
        CellState.DERIVED,
        "290",
        LineageMethod.FY_MINUS_NINE_MONTHS,
    )
    assert q4.known_from == parse_cutoff(accepted)


def test_an_amendment_changes_an_old_value_only_from_its_filing_on(warehouse: Warehouse) -> None:
    every = warehouse.history(ALPHA, "revenue", 2020, FiscalPeriod.Q4)
    # Missing (period not reported yet) from the first 2020 10-Q to the 10-K.
    assert every[0].value.value is None
    assert every[0].change is ValueChange.FIRST_KNOWN
    history = [h for h in every if h.value.value is not None]
    assert [(h.value.value, h.change) for h in history] == [
        ("290", ValueChange.VALUE_FILLED),
        ("270", ValueChange.VALUE_REVISED),  # the 10-K/A restates the year
        ("280", ValueChange.VALUE_REVISED),  # next year's Q3 10-Q restates nine months
        ("280", ValueChange.CONFIRMED),  # next year's 10-K repeats the restated year
    ]
    assert history[0].known_to == history[1].known_from == parse_cutoff("2021-06-15T10:00-04:00")
    # The restated year minus nine months nobody restated yet: two different bases.
    assert QualityFlag.MIXED_VINTAGE in history[1].value.flags
    assert QualityFlag.MIXED_VINTAGE not in history[2].value.flags
    assert {QualityFlag.RESTATED} <= set(history[2].value.flags)
    assert history[2].value.original_value == "290"
    assert values(warehouse, ALPHA, "2021-03-01")[(2020, FiscalPeriod.FY)] == "1100"
    assert values(warehouse, ALPHA, "2021-07-01")[(2020, FiscalPeriod.FY)] == "1080"
    original = values(warehouse, ALPHA, "2022-06-30", view=KnowledgeView.ORIGINAL)
    assert original[(2020, FiscalPeriod.FY)] == "1100"
    assert original[(2020, FiscalPeriod.Q4)] == "290"
    # Latest is hindsight: the same answer whatever the moment.
    early = values(warehouse, ALPHA, "2020-01-01", view=KnowledgeView.LATEST)
    assert early[(2020, FiscalPeriod.Q4)] == "280"


def test_cumulative_cash_flow_becomes_quarters_never_the_year(warehouse: Warehouse) -> None:
    cfo = values(warehouse, ALPHA, "2021-03-01", metric="cfo")
    assert cfo[(2020, FiscalPeriod.Q2)] == "80"  # H1 150 - Q1 70
    assert cfo[(2020, FiscalPeriod.Q3)] == "90"  # 9M 240 - H1 150
    assert cfo[(2020, FiscalPeriod.Q4)] == "100"  # FY 340 - 9M 240, not 340
    assert cfo[(2020, FiscalPeriod.FY)] == "340"
    panel = build_panel(warehouse, [ALPHA], parse_cutoff("2021-06-30"), quarters=8)
    assert cell(panel, ALPHA, "2020Q4", "cfo").method is LineageMethod.FY_MINUS_NINE_MONTHS
    ttm = {(f.calendar_quarter, f.name): f for f in build_features(panel.cells)}
    assert ttm[("2021Q1", "ttm_cfo")].value == Decimal(345)  # 75 + 100 + 90 + 80
    assert not ttm[("2021Q2", "ttm_cfo")].mask  # 2021Q2 not filed at the cutoff


def test_missing_rnd_stays_masked_and_never_becomes_zero(warehouse: Warehouse) -> None:
    panel = build_panel(warehouse, [ALPHA], parse_cutoff("2021-12-31"), quarters=8)
    rnd = [c for c in panel.cells if c.metric == "rnd"]
    assert {c.state for c in rnd} == {CellState.NOT_REPORTED, CellState.NOT_YET_FILED}
    assert all(c.value is None and not c.mask and c.reason for c in rnd)
    features = [f for f in build_features(panel.cells) if f.name == "ttm_rnd"]
    assert features
    assert all(f.value is None and not f.mask for f in features)


def test_a_deregistered_company_stays_in_the_panel_as_inactive(warehouse: Warehouse) -> None:
    before = build_panel(warehouse, [BETA], parse_cutoff("2019-12-01"), quarters=4)
    assert CellState.INACTIVE not in {c.state for c in before.cells}
    # Form 15 public, Q4 report not overdue yet: it may cover one class of securities.
    pending = build_panel(warehouse, [BETA], parse_cutoff("2020-02-15"), quarters=4)
    assert cell(pending, BETA, "2019Q4").state is CellState.NOT_YET_FILED
    panel = build_panel(warehouse, [BETA], parse_cutoff("2020-06-30"), quarters=4)
    assert cell(panel, BETA, "2019Q3").value == "103"
    for quarter in ("2019Q4", "2020Q1", "2020Q2"):
        assert cell(panel, BETA, quarter).state is CellState.INACTIVE
    assert len(panel.cells) == 4 * 16  # no survivorship: the company is not dropped
    kinds = {a.kind for a in warehouse.alerts([BETA])}
    assert {
        AlertKind.DEREGISTRATION,
        AlertKind.REPORT_OUT_OF_ORDER,
        AlertKind.LATE_REPORT,
        AlertKind.AMENDMENT_BEFORE_ORIGINAL,
    } <= kinds


def test_a_53_week_year_maps_to_the_right_calendar_quarter(warehouse: Warehouse) -> None:
    panel = build_panel(warehouse, [GAMMA], parse_cutoff("2021-03-31"), quarters=5)
    q4 = cell(panel, GAMMA, "2020Q4")
    assert (q4.period_start, q4.period_end, q4.value) == (
        date(2020, 9, 27),
        date(2021, 1, 2),
        "1400",
    )
    assert QualityFlag.FIFTY_THREE_WEEKS in q4.flags
    assert cell(panel, GAMMA, "2020Q1").period_end == date(2020, 3, 28)
    # Accepted four days after its filing date: public from the acceptance.
    assert cell(panel, GAMMA, "2020Q4").known_from == datetime(2021, 3, 1, 21, tzinfo=UTC)
    early = build_panel(warehouse, [GAMMA], parse_cutoff("2021-02-26"), quarters=4)
    assert cell(early, GAMMA, "2020Q4").state is CellState.NOT_YET_FILED
    assert AlertKind.ACCEPTED_AFTER_FILING_DATE in {a.kind for a in warehouse.alerts([GAMMA])}


def test_a_provisional_year_places_quarters_before_its_10k(warehouse: Warehouse) -> None:
    panel = build_panel(warehouse, [GAMMA], parse_cutoff("2020-05-15"), quarters=2)
    q1 = cell(panel, GAMMA, "2020Q1")
    assert (q1.state, q1.fiscal_year, q1.value) == (CellState.OBSERVED, 2020, "1000")


def test_estimates_never_enter_a_view(warehouse: Warehouse) -> None:
    years = values(warehouse, ALPHA, "2021-12-31")
    assert years[(2021, FiscalPeriod.FY)] is None
    assert values(warehouse, ALPHA, "2022-12-31")[(2021, FiscalPeriod.FY)] == "1260"
    blocking = [a for a in warehouse.alerts([ALPHA]) if a.severity is QualitySeverity.BLOCKING]
    assert [(a.kind, a.period_end) for a in blocking] == [
        (AlertKind.PERIOD_AFTER_FILING, date(2021, 12, 31))
    ]


def test_index_problems_raise_warnings(warehouse: Warehouse) -> None:
    kinds = {a.kind for a in warehouse.alerts([ALPHA])}
    assert {
        AlertKind.MISSING_ACCEPTANCE,
        AlertKind.FILING_DATE_MISMATCH,
        AlertKind.QUARTERS_DO_NOT_SUM,
    } <= kinds


# ------------------------------------------------------------------ identity over time


def test_names_follow_their_official_dates(warehouse: Warehouse) -> None:
    records = warehouse.attributes([ALPHA])
    name = EntityAttributeName.NAME
    assert attribute_as_of(records, ALPHA, name, parse_cutoff("2020-05-31"))[0] == (
        "ALPHA HOLDINGS INC",
    )
    assert attribute_as_of(records, ALPHA, name, parse_cutoff("2020-06-01"))[0] == ("ALPHA CORP",)
    ticker, reason = attribute_as_of(
        records, ALPHA, EntityAttributeName.TICKER, day_end(date(2021, 1, 1))
    )
    assert ticker == ()
    assert reason
    assert "2026-10-29" in reason
    assert attribute_as_of(records, ALPHA, EntityAttributeName.TICKER, BUILT)[0] == ("ALPX",)


def test_a_renamed_ticker_and_its_reuse_resolve_by_date() -> None:
    def ticker(cik: str, value: str, start: str, end: str | None = None) -> EntityAttribute:
        return EntityAttribute(
            cik=cik,
            attribute=EntityAttributeName.TICKER,
            value=value,
            effective_from=date.fromisoformat(start),
            effective_to=date.fromisoformat(end) if end else None,
            observed_at=OBSERVED,
            source="synthetic ticker history",
        )

    records = [
        ticker(ALPHA, "ALP", "2010-01-04", "2020-06-01"),
        ticker(ALPHA, "ALPX", "2020-06-01"),
        ticker("0000000014", "ALP", "2022-03-01"),
    ]
    assert resolve_ticker(records, "ALP", parse_cutoff("2020-05-31")) == [ALPHA]
    assert resolve_ticker(records, "ALP", parse_cutoff("2021-01-01")) == []
    assert resolve_ticker(records, "ALPX", parse_cutoff("2021-01-01")) == [ALPHA]
    assert resolve_ticker(records, "ALP", parse_cutoff("2023-01-01")) == ["0000000014"]


# ------------------------------------------------------------------ no leakage


def _knowledge_points(warehouse: Warehouse, cik: str) -> list[datetime]:
    return sorted({v.known_from for v in warehouse.all_values(cik)})


@pytest.mark.parametrize("company", [alpha, beta, gamma])
def test_as_of_equals_normalizing_only_what_was_public(warehouse: Warehouse, company: Any) -> None:
    built = company()
    inputs = built.inputs()
    index = prepare(inputs).filings
    known = {f.accession: f.known_at for f in index}
    for point in _knowledge_points(warehouse, built.cik):
        for moment in (point - timedelta(microseconds=1), point):
            public = [
                f
                for f in inputs.facts
                if f.end <= f.filed and known.get(f.accession, day_end(f.filed)) <= moment
            ]
            day = eastern_date(moment)
            expected = (
                {}
                if not public
                else {
                    (r.metric, r.fiscal_year, r.fiscal_period, r.revision): r
                    for r in CompanyNormalizer(built.cik, public, provisional=True).normalize()
                    if r.period_end <= day
                }
            )
            found = {
                (
                    v.value.metric,
                    v.value.fiscal_year,
                    v.value.fiscal_period,
                    v.value.revision,
                ): v.value
                for view in (KnowledgeView.VINTAGE, KnowledgeView.ORIGINAL)
                for v in warehouse.as_of(built.cik, moment, view=view)
            }
            assert found == expected, moment


def _poisoned() -> Company:
    """Alpha plus filings after the end of 2021 that rewrite its past."""
    c = alpha()
    late = c.filing(50, "10-K/A", "2022-03-01", "2020-12-31", "2022-03-01T15:00:00.000Z")
    c.fact("Revenues", 999_999_999, year(2020), late, fy=2020)
    c.fact("Revenues", 999_999_999, q(2021, 3), late)
    c.fact("NetCashProvidedByUsedInOperatingActivities", -5, ytd(2020, 9), late)
    c.fact("ResearchAndDevelopmentExpense", 77, q(2021, 2), late)
    future = c.filing(51, "10-Q", "2022-04-28", "2022-03-31", "2022-04-28T20:00:00.000Z")
    c.fact("Revenues", 1, q(2022, 1), future)
    c.fact("Revenues", 2, q(2021, 1), future)
    c.filing(52, "15-12B", "2022-05-01", None, "2022-05-01T15:00:00.000Z")
    return c


def test_later_filings_never_change_an_earlier_snapshot(warehouse: Warehouse) -> None:
    cutoff = parse_cutoff("2021-12-31")
    options: dict[str, Any] = {"cutoff_label": "2021-12-31", "created_at": BUILT, "quarters": 8}
    base = make_snapshot(warehouse, [ALPHA, BETA, GAMMA], cutoff, **options)
    again = make_snapshot(warehouse, [ALPHA, BETA, GAMMA], cutoff, **options)
    assert base.body == again.body
    assert base.manifest.snapshot_id == again.manifest.snapshot_id
    poisoned = build(_poisoned(), beta(), gamma())
    truncated = build(alpha(), beta(), gamma(), known_by=cutoff)
    for other in (poisoned, truncated):
        snapshot = make_snapshot(other, [ALPHA, BETA, GAMMA], cutoff, **options)
        assert snapshot.body == base.body
        assert snapshot.features == base.features
    later = parse_cutoff("2022-06-30")
    changed = make_snapshot(poisoned, [ALPHA], later, **{**options, "cutoff_label": "2022-06-30"})
    plain = make_snapshot(warehouse, [ALPHA], later, **{**options, "cutoff_label": "2022-06-30"})
    assert changed.manifest.sha256 != plain.manifest.sha256


def test_a_snapshot_after_the_archive_download_is_refused(warehouse: Warehouse) -> None:
    with pytest.raises(ValueError, match="after the archive was downloaded"):
        make_snapshot(
            warehouse,
            [ALPHA],
            parse_cutoff("2026-10-29"),
            cutoff_label="2026-10-29",
            created_at=BUILT,
        )


def test_a_panel_with_a_value_from_after_its_cutoff_is_refused(warehouse: Warehouse) -> None:
    cutoff = parse_cutoff("2021-03-01")
    panel = build_panel(warehouse, [ALPHA], cutoff, quarters=4)
    check_point_in_time(panel)
    leaked = Panel(parse_cutoff("2021-02-01"), panel.view, panel.cells, panel.sources)
    with pytest.raises(LeakageError):
        check_point_in_time(leaked)
    with pytest.raises(ValueError, match="point-in-time"):
        build_panel(warehouse, [ALPHA], cutoff, view=KnowledgeView.LATEST)


# ------------------------------------------------------------------ snapshot files


def test_snapshot_files_lineage_and_coverage_counts(warehouse: Warehouse, tmp_path: Path) -> None:
    cutoff = parse_cutoff("2021-12-31")
    snapshot = make_snapshot(
        warehouse,
        [ALPHA, BETA, GAMMA],
        cutoff,
        cutoff_label="2021-12-31",
        created_at=BUILT,
        quarters=8,
    )
    manifest = snapshot.manifest
    assert manifest.cells == 3 * 8 * 16 == sum(c.cells for c in manifest.state_counts)
    assert manifest.snapshot_id == f"pit-20211231-{manifest.sha256[:12]}"
    folder = write_snapshot(snapshot, warehouse, tmp_path)
    assert {p.name for p in folder.iterdir()} == {
        "snapshot.jsonl",
        "panel.csv",
        "features.csv",
        "lineage.jsonl",
        "manifest.json",
    }
    PitSnapshotManifest.model_validate_json((folder / "manifest.json").read_text(encoding="utf-8"))
    lineage = [json.loads(line) for line in (folder / "lineage.jsonl").read_text().splitlines()]
    assert len(lineage) == sum(c.mask for c in snapshot.panel.cells)
    for row in lineage:
        assert row["raw_file"]["sha256"] == "0" * 64
        for source in row["sources"]:
            assert source["public_at"] <= "2022-01-01T04:59:59.999999Z"
            assert source["filing_url"].startswith("https://www.sec.gov/Archives/edgar/data/")
    companies = [json.loads(x) for x in snapshot.body.decode().splitlines() if '"company"' in x]
    beta_now = next(c for c in companies if c["cik"] == BETA)
    assert beta_now["status"] == "deregistration_filed"
    rows = lineage_rows(snapshot, warehouse)
    q4 = next(r for r in rows if r["cik"] == ALPHA and r["calendar_quarter"] == "2021Q3")
    assert [s["value"] for s in q4["sources"]] == ["320"]


# ------------------------------------------------------------------ commands


def _store(archive: RawArchive, dataset: str, key: str, cik: str, payload: dict[str, Any]) -> None:
    part = archive.tmp_dir / f"{dataset}.part"
    part.write_text(json.dumps(payload), encoding="utf-8")

    def describe(sha: str, size: int, path: str) -> RawObject:
        return RawObject(
            source_id="sec-edgar",
            dataset_id=dataset,
            key=key,
            cik=cik,
            url="https://data.sec.gov/fixture",
            path=path,
            sha256=sha,
            size_bytes=size,
            file_format="json",
            content_encoding="identity",
            http_status=200,
            downloaded_at=OBSERVED,
            run_id="fixture",
            licence="fixture",
            terms_checked_on=date(2026, 10, 29),
            catalog_version="0.9.0",
        )

    archive.store(part, dataset_id=dataset, key=key, file_format="json", describe=describe)


def test_the_commands_build_query_snapshot_and_check_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in [n for n in os.environ if n.startswith("MULTIVERSE_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    archive = RawArchive(Path("var/raw"), budget_bytes=10_000_000)
    archive.tmp_dir.mkdir(parents=True)
    company = alpha()
    _store(archive, "sec-companyfacts", f"CIK{ALPHA}", ALPHA, company.companyfacts())
    _store(archive, "sec-submissions", f"CIK{ALPHA}", ALPHA, company.submissions())
    assert cli.main(["build", "--cik", "11"]) == 0
    assert Path("var/data/pit/warehouse.sqlite").exists()
    assert cli.main(["as-of", "--cik", "11", "--metric", "revenue", "--at", "2021-12-31"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert any(line.startswith("FY2021 Q3") and " 320 " in line for line in out)
    assert any(line.startswith("FY2021 FY") and " - (" in line for line in out)  # missing
    assert (
        cli.main(
            [
                "history",
                "--cik",
                "11",
                "--metric",
                "revenue",
                "--fiscal-year",
                "2020",
                "--period",
                "Q4",
            ]
        )
        == 0
    )
    assert "value_revised" in capsys.readouterr().out
    assert cli.main(["entity", "--cik", "11", "--at", "2020-01-01"]) == 0
    assert "ALPHA HOLDINGS INC" in capsys.readouterr().out
    assert cli.main(["snapshot", "--cutoff", "2021-12-31", "--quarters", "8"]) == 0
    first = capsys.readouterr().out.split()[0]
    assert cli.main(["snapshot", "--cutoff", "2021-12-31", "--quarters", "8"]) == 0
    assert capsys.readouterr().out.split()[0] == first
    assert Path(f"var/data/pit/snapshots/{first}/lineage.jsonl").exists()
    assert cli.main(["coverage", "--cutoff", "2021-12-31", "--quarters", "8"]) == 0
    page = Path("var/data/pit/coverage/coverage.html").read_text(encoding="utf-8")
    style = page.split("<style>")[1].split("</style>")[0]
    assert style.count("{") == style.count("}")  # the dark-mode block is closed
    assert "Point-in-time coverage at 2021-12-31" in page
    assert first in page
    assert cli.main(["alerts", "--severity", "blocking"]) == 0
    assert "period_after_filing" in capsys.readouterr().out
    assert (
        cli.main(["leakage-check", "--cutoff", "2021-12-31", "--quarters", "8", "--cik", "11"]) == 0
    )
    assert "identical: yes" in capsys.readouterr().out
    assert cli.main(["snapshot", "--cutoff", "2999-01-01"]) == 2
    assert cli.main(["--db", "missing.sqlite", "alerts"]) == 2
