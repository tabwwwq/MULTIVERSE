"""Gate B audit (Stage 14) on a synthetic steady filer. Every value here is invented.

The filer reports seven calendar years: three 10-Qs (quarterly revenue, cash flow year
to date) and a 10-K (the year) each year, in the shape of Company Facts and submissions.
"""

import json
import os
import shutil
import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.macro import AvailabilityBasis, MacroObservation
from multiverse_contracts.metrics import LineageMethod
from multiverse_contracts.normalized import FiscalPeriod
from multiverse_contracts.pit import AlertKind, ChronologyAlert
from multiverse_contracts.quality import CheckStatus, ExampleCount
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_contracts.universe import RuleCount, UniverseCompany, UniverseManifest
from multiverse_pipelines.audit import cli as audit_cli
from multiverse_pipelines.audit.checks import (
    CHECKS,
    Current,
    cumulative_cashflow,
    load,
    source_conflicts,
    survivorship,
)
from multiverse_pipelines.audit.examples import count_examples, examples_hash, shift
from multiverse_pipelines.audit.run import (
    leakage_sample,
    macro_check,
    reconciliation_check,
    sample_size_check,
)
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit import cli as pit_cli
from multiverse_pipelines.pit.build import CompanyInputs, prepare
from multiverse_pipelines.pit.clock import parse_cutoff
from multiverse_pipelines.pit.panel import build_panel
from multiverse_pipelines.pit.snapshot import entities_as_of
from multiverse_pipelines.pit.warehouse import Warehouse, decode, encode, make_dictionary
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.xbrl.facts import facts_from_companyfacts

CIK = "0000000031"
OBSERVED = datetime(2026, 10, 29, 19, tzinfo=UTC)
BUILT = datetime(2026, 10, 30, tzinfo=UTC)
YEARS = range(2012, 2019)
ENDS = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def revenue(year: int, quarter: int, jump: bool) -> int:
    value = 100 + 2 * ((year - 2012) * 4 + quarter)
    return value * 3 if jump and (year, quarter) == (2016, 2) else value


def steady(*, jump: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Company Facts and submissions of a filer with seven calm years."""
    filings: list[dict[str, Any]] = []
    rows: dict[str, list[dict[str, Any]]] = {
        "Revenues": [],
        "NetCashProvidedByUsedInOperatingActivities": [],
    }
    number = 0

    def filing(form: str, filed: date, report: date) -> str:
        nonlocal number
        number += 1
        accession = f"{CIK}-{filed:%y}-{number:06d}"
        accepted = f"{filed.isoformat()}T20:00:00.000Z"
        filings.append(
            {
                "accessionNumber": accession,
                "form": form,
                "filingDate": filed.isoformat(),
                "reportDate": report.isoformat(),
                "acceptanceDateTime": accepted,
                "isXBRL": 1,
                "items": "",
            }
        )
        return accession

    def fact(
        tag: str,
        value: int,
        start: date,
        end: date,
        accession: str,
        form: str,
        filed: date,
        fy: int | None,
    ) -> None:
        rows[tag].append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "val": value,
                "accn": accession,
                "fy": fy,
                "fp": None,
                "form": form,
                "filed": filed.isoformat(),
            }
        )

    for year in YEARS:
        cumulative = 0
        for quarter in (1, 2, 3):
            month, day = ENDS[quarter]
            end = date(year, month, day)
            filed = end + timedelta(days=35)
            accession = filing("10-Q", filed, end)
            start = date(year, 3 * quarter - 2, 1)
            fact(
                "Revenues", revenue(year, quarter, jump), start, end, accession, "10-Q", filed, None
            )
            cumulative += 30 + quarter
            fact(
                "NetCashProvidedByUsedInOperatingActivities",
                cumulative,
                date(year, 1, 1),
                end,
                accession,
                "10-Q",
                filed,
                None,
            )
        filed = date(year + 1, 2, 15)
        accession = filing("10-K", filed, date(year, 12, 31))
        annual = sum(revenue(year, q, jump) for q in (1, 2, 3, 4))
        fact(
            "Revenues", annual, date(year, 1, 1), date(year, 12, 31), accession, "10-K", filed, year
        )
        fact(
            "NetCashProvidedByUsedInOperatingActivities",
            cumulative + 34,
            date(year, 1, 1),
            date(year, 12, 31),
            accession,
            "10-K",
            filed,
            year,
        )
    companyfacts = {
        "cik": int(CIK),
        "entityName": "STEADY CO",
        "facts": {"us-gaap": {tag: {"units": {"USD": values}} for tag, values in rows.items()}},
    }
    columns = (
        "accessionNumber",
        "form",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "isXBRL",
        "items",
    )
    submissions = {
        "cik": str(int(CIK)),
        "name": "STEADY CO",
        "tickers": [],
        "exchanges": [],
        "sic": "3674",
        "formerNames": [],
        "filings": {"recent": {c: [f[c] for f in filings] for c in columns}, "files": []},
    }
    return companyfacts, submissions


def raw(dataset: str) -> RawObject:
    return RawObject(
        source_id="sec-edgar",
        dataset_id=dataset,
        key=f"CIK{CIK}",
        cik=CIK,
        url="https://data.sec.gov/fixture",
        path=f"sec/x/CIK{CIK}/{'0' * 64}.json",
        sha256="0" * 64,
        size_bytes=1,
        file_format="json",
        content_encoding="identity",
        http_status=200,
        downloaded_at=OBSERVED,
        run_id="fixture",
        licence="fixture",
        terms_checked_on=date(2026, 10, 29),
        catalog_version="0.12.0",
    )


def warehouse_of(*, jump: bool = False) -> Warehouse:
    companyfacts, submissions = steady(jump=jump)
    inputs = CompanyInputs(
        cik=CIK,
        facts=facts_from_companyfacts(companyfacts),
        submissions=submissions,
        pages=[],
        observed_at=OBSERVED,
        files=[raw("sec-companyfacts")],
    )
    item = prepare(inputs)
    built = Warehouse.create(None, built_at=BUILT)
    built.add_company(item.history, item.filings, item.attributes, item.alerts, item.files)
    return built


@pytest.fixture(scope="module")
def warehouse() -> Iterator[Warehouse]:
    built = warehouse_of()
    yield built
    built.close()


def test_examples_have_public_history_and_a_released_target(warehouse: Warehouse) -> None:
    cutoff = parse_cutoff("2018-06-30")
    counts, examples = count_examples(warehouse, [CIK], "revenue", cutoff, date(2013, 3, 31))
    by = {(c.history_quarters, c.horizon_quarters): c for c in counts}
    assert by[(8, 1)].examples > by[(8, 20)].examples >= 0
    assert by[(20, 20)].examples == 0  # 20 quarters of history and 5 years ahead do not fit
    for example in examples:
        assert example.target_quarter == shift(example.origin, example.horizon)
        assert example.target_quarter > example.origin
        # Nothing released after the data cutoff: Q4 2017 (10-K of Feb 2018) yes, Q2 2018 no.
        assert example.target_quarter <= date(2018, 3, 31)
    assert examples_hash(examples) == examples_hash(list(reversed(examples)))
    # The first origin with 8 public quarters: Q4 2013 is public only from February 2014.
    first = min(e.origin for e in examples if e.history == 8)
    assert first == date(2014, 3, 31)


def data_of(warehouse: Warehouse) -> Any:
    cutoff = parse_cutoff("2019-06-30")
    panel = build_panel(warehouse, [CIK], cutoff, quarters=28)
    candidates = {c.cik: c for c in SOURCE_CATALOG.candidates}
    return load(warehouse, [CIK], {CIK: "Steady"}, candidates, cutoff, panel)


def test_the_checks_on_a_clean_filer(warehouse: Warehouse) -> None:
    results = {check(data_of(warehouse)).check_id: check(data_of(warehouse)) for check in CHECKS}
    assert results["duplicated_company_quarter"].status is CheckStatus.PASS
    assert results["currency_fx"].status is CheckStatus.PASS
    assert results["unrealistic_jumps"].status is CheckStatus.PASS
    assert results["cumulative_cashflow"].status is CheckStatus.PASS
    assert results["revenue_gaps"].status is CheckStatus.PASS
    assert results["future_revisions"].status is CheckStatus.PASS
    assert results["survivor_only_sample"].status is CheckStatus.WARNING


def test_a_jump_is_found_and_named() -> None:
    jumpy = warehouse_of(jump=True)
    data = data_of(jumpy)
    found = next(check(data) for check in CHECKS if check.__name__ == "jumps")
    assert found.status is CheckStatus.WARNING
    assert any("2016Q2" in f for f in found.findings)
    jumpy.close()


def reconciliation_file(tmp_path: Path, entries: int, wrong: bool = False) -> Path:
    items = []
    for year in list(YEARS)[:entries]:
        q4 = revenue(year, 4, False) + (1 if wrong and year == 2012 else 0)
        items.append(
            {
                "company": "Steady",
                "cik": CIK,
                "metric": "revenue",
                "fiscal_year": year,
                "fiscal_period": "Q4",
                "view": "original",
                "expected": str(q4),
            }
        )
    while len(items) < entries:
        items.append({**items[0]})
    path = tmp_path / "manual.json"
    path.write_text(json.dumps({"reconciliations": items}), encoding="utf-8")
    return path


def test_reconciliation_needs_ten_matching_amounts(warehouse: Warehouse, tmp_path: Path) -> None:
    cutoff = parse_cutoff("2019-06-30")
    assert (
        reconciliation_check(warehouse, reconciliation_file(tmp_path, 10), cutoff).status
        is CheckStatus.PASS
    )
    wrong = reconciliation_check(warehouse, reconciliation_file(tmp_path, 10, wrong=True), cutoff)
    assert wrong.status is CheckStatus.FAIL
    assert any("MISMATCH" in f for f in wrong.findings)
    assert (
        reconciliation_check(warehouse, reconciliation_file(tmp_path, 9), cutoff).status
        is CheckStatus.BLOCKED
    )
    assert (
        reconciliation_check(warehouse, tmp_path / "none.json", cutoff).status
        is CheckStatus.BLOCKED
    )


def test_size_and_macro_block_honestly() -> None:
    small = [
        ExampleCount(history_quarters=12, horizon_quarters=4, examples=40, companies=1, origins=40)
    ]
    big = [
        ExampleCount(
            history_quarters=12, horizon_quarters=4, examples=1200, companies=40, origins=60
        )
    ]
    assert sample_size_check(small, 1).status is CheckStatus.BLOCKED
    assert sample_size_check(big, 40).status is CheckStatus.PASS
    assert macro_check(None).status is CheckStatus.BLOCKED


def _store(archive: RawArchive, dataset: str, payload: dict[str, Any]) -> None:
    part = archive.tmp_dir / f"{dataset}.part"
    part.write_text(json.dumps(payload), encoding="utf-8")

    def describe(sha: str, size: int, path: str) -> RawObject:
        return raw(dataset).model_copy(update={"sha256": sha, "size_bytes": size, "path": path})

    archive.store(part, dataset_id=dataset, key=f"CIK{CIK}", file_format="json", describe=describe)


def test_the_gate_command_writes_a_blocked_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in [n for n in os.environ if n.startswith("MULTIVERSE_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    archive = RawArchive(Path("var/raw"), budget_bytes=10_000_000)
    archive.tmp_dir.mkdir(parents=True)
    companyfacts, submissions = steady()
    _store(archive, "sec-companyfacts", companyfacts)
    _store(archive, "sec-submissions", submissions)
    assert pit_cli.main(["build", "--cik", CIK]) == 0
    reconciliation = reconciliation_file(tmp_path, 10)
    code = audit_cli.main(
        [
            "run",
            "--cutoff",
            "2019-06-30",
            "--leakage-cutoff",
            "2016-12-31",
            "--reconciliation",
            str(reconciliation),
        ]
    )
    assert code == 3  # blocked: one company, no real macro data
    out = capsys.readouterr().out
    assert "pass     Leakage proof" in out
    assert "pass     Manual reconciliation" in out
    folder = Path("var/data/gate")
    assert {p.name for p in folder.iterdir()} == {
        "manifest.json",
        "examples.csv",
        "data-card.md",
        "coverage.html",
    }
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "blocked"
    assert manifest["dataset_id"].endswith(manifest["sha256"][:12])
    page = (folder / "coverage.html").read_text(encoding="utf-8")
    style = page.split("<style>")[1].split("</style>")[0]
    assert style.count("{") == style.count("}")
    card = (folder / "data-card.md").read_text(encoding="utf-8")
    assert "## Usable size" in card
    assert "not in downloaded files" in card
    shutil.rmtree(folder)
    assert audit_cli.main(["run", "--cutoff", "2019-06-30"]) in (2, 3)


def test_jumps_threshold_is_relative() -> None:
    assert Decimal(revenue(2016, 2, True)) / Decimal(revenue(2016, 1, True)) - 1 > Decimal("0.5")


def test_payloads_shrink_with_a_dictionary_and_decode_unchanged(
    warehouse: Warehouse, tmp_path: Path
) -> None:
    values = warehouse.all_values(CIK)
    dictionary = make_dictionary(values)
    assert 0 < len(dictionary) <= 32 * 1024
    plain = sum(len(v.model_dump_json()) for v in values)
    packed = sum(len(encode(v, dictionary)) for v in values)
    assert packed * 4 < plain
    assert all(decode(encode(v, dictionary), dictionary) == v for v in values)
    assert decode(encode(values[0], b""), b"") == values[0]
    old = tmp_path / "old.sqlite"
    sqlite3.connect(old).execute("CREATE TABLE meta (key TEXT, value TEXT)").connection.close()
    with pytest.raises(ValueError, match="earlier version"):
        Warehouse.open(old)


def test_current_values_and_revision_counts_come_from_the_query(warehouse: Warehouse) -> None:
    current = warehouse.current(CIK)
    assert current
    assert all(v.known_to is None and v.value.revision.value == "latest" for v in current)
    revised = sum(warehouse.revised(CIK).values())
    assert revised == sum(
        1
        for v in warehouse.all_values(CIK)
        if v.value.revision.value == "latest" and v.change.value == "value_revised"
    )


def test_the_leakage_sample_is_seeded_and_keeps_the_candidates() -> None:
    ciks = [f"{n:010d}" for n in range(1, 201)]
    chosen = leakage_sample(ciks, ["0000000150", "0000009999"], 20)
    assert len(chosen) == 20
    assert "0000000150" in chosen
    assert chosen == leakage_sample(list(reversed(ciks)), ["0000000150"], 20)
    assert leakage_sample(ciks[:5], [], 20) == ciks[:5]


def test_macro_check_names_series_that_start_after_the_first_origin() -> None:
    store = MacroStore.create(None, synthetic=False, built_at=BUILT)
    store.register(["fred:GDPC1"])
    store.add(
        [
            MacroObservation(
                series_id="fred:GDPC1",
                period_start=date(2005, 1, 1),
                period_end=date(2005, 3, 31),
                value="100",
                available_from=datetime(2005, 4, 28, 13, tzinfo=UTC),
                basis=AvailabilityBasis.VINTAGE,
                source_vintage=date(2005, 4, 28),
            ),
            MacroObservation(
                series_id="wb:USA.NY.GDP.MKTP.KD.ZG",
                period_start=date(2005, 1, 1),
                period_end=date(2005, 12, 31),
                value="3.5",
                available_from=datetime(2026, 10, 1, 4, tzinfo=UTC),
                basis=AvailabilityBasis.SNAPSHOT,
                source_vintage=date(2026, 9, 30),
            ),
        ]
    )
    check = macro_check(store)
    assert check.status is CheckStatus.WARNING
    assert any(
        f.startswith("wb:USA.NY.GDP.MKTP.KD.ZG: first available 2026-10-01") for f in check.findings
    )
    assert not any(f.startswith("fred:GDPC1: first") for f in check.findings)
    assert any(f == "fred:UNRATE: not in the store" for f in check.findings)
    store.close()


def test_a_universe_counts_its_deregistered_companies(warehouse: Warehouse) -> None:
    data = data_of(warehouse)
    stub = UniverseCompany(
        cik=CIK,
        name="Steady",
        sic="3674",
        division="D",
        xbrl_10k=7,
        xbrl_10q=21,
        first_xbrl_filed=date(2012, 5, 1),
        last_filed=date(2019, 2, 1),
        deregistered=True,
        candidate=False,
    )
    data.universe = UniverseManifest.model_construct(
        universe_id="sec-1-1",
        rules=(RuleCount(rule="eligible", remaining=5),),
        companies=(stub,),
    )
    check = survivorship(data)
    assert check.status is CheckStatus.WARNING
    assert {m.name: m.value for m in check.measures}["deregistered (Form 15)"] == "1"
    assert check.findings == ("Steady: Form 15, last filing 2019-02-01",)


def test_q4_equal_to_the_year_fails_only_when_not_derived(warehouse: Warehouse) -> None:
    data = data_of(warehouse)

    def cfo(period: FiscalPeriod, value: str, month: int, method: LineageMethod) -> Current:
        end = date(2030, month, 28 if month < 12 else 31)
        return Current("cfo", 2030, period, end, value, None, "USD", (), method)

    reported, derived = LineageMethod.REPORTED, LineageMethod.FY_MINUS_NINE_MONTHS
    year = cfo(FiscalPeriod.FY, "-100", 12, reported)

    def quarters(value: str) -> list[Current]:
        periods = [(FiscalPeriod.Q1, 3), (FiscalPeriod.Q2, 6), (FiscalPeriod.Q3, 9)]
        return [cfo(p, value, m, reported) for p, m in periods]

    # Nothing in the first nine months: Q4 = year minus zero, by arithmetic.
    data.current = {CIK: [*quarters("0"), cfo(FiscalPeriod.Q4, "-100", 12, derived), year]}
    check = cumulative_cashflow(data)
    assert check.status is CheckStatus.PASS
    measures = {m.name: m.value for m in check.measures}
    assert measures["Q4 equal to the year, nine months filed as zero"] == "1"
    # The annual total taken as Q4: an error of the pipeline.
    data.current = {CIK: [*quarters("10"), cfo(FiscalPeriod.Q4, "-100", 12, reported), year]}
    assert cumulative_cashflow(data).status is CheckStatus.FAIL


def test_estimates_left_out_of_every_view_are_a_warning(warehouse: Warehouse) -> None:
    data = data_of(warehouse)
    data.alerts = [
        ChronologyAlert(
            kind=AlertKind.PERIOD_AFTER_FILING,
            severity=QualitySeverity.BLOCKING,
            cik=CIK,
            accession="0000000031-12-000001",
            concept="us-gaap:LongTermDebtNoncurrent",
            period_end=date(2018, 6, 30),
            detail="us-gaap:LongTermDebtNoncurrent for a period ending 2018-06-30 was filed on "
            "2012-08-14: an estimate, left out of every view",
        )
    ]
    check = source_conflicts(data)
    assert check.status is CheckStatus.WARNING
    assert {m.name: m.value for m in check.measures}["blocking alerts not guarded"] == "0"
    assert check.companies == (CIK,)


def test_before_its_first_filing_a_company_shows_nothing(warehouse: Warehouse) -> None:
    # How the current name is dated depends on the first filing, a later fact: before it,
    # every attribute is empty with one reason, so a rebuild from the past matches.
    (entity,) = entities_as_of(warehouse, [CIK], parse_cutoff("2005-12-31"))
    assert entity["status"] == "no_filings_yet"
    for attribute in ("name", "ticker", "exchange", "sic"):
        assert entity[attribute] == []
        assert entity[f"{attribute}_unknown"] == "no filings by this date"
    (later,) = entities_as_of(warehouse, [CIK], parse_cutoff("2019-06-30"))
    assert later["status"] != "no_filings_yet"
