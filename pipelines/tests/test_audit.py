"""Gate B audit (Stage 14) on a synthetic steady filer. Every value here is invented.

The filer reports seven calendar years: three 10-Qs (quarterly revenue, cash flow year
to date) and a 10-K (the year) each year, in the shape of Company Facts and submissions.
"""

import json
import os
import shutil
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from multiverse_contracts.quality import CheckStatus, ExampleCount
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_pipelines.audit import cli as audit_cli
from multiverse_pipelines.audit.checks import CHECKS, load
from multiverse_pipelines.audit.examples import count_examples, examples_hash, shift
from multiverse_pipelines.audit.run import (
    macro_check,
    reconciliation_check,
    sample_size_check,
)
from multiverse_pipelines.pit import cli as pit_cli
from multiverse_pipelines.pit.build import CompanyInputs, prepare
from multiverse_pipelines.pit.clock import parse_cutoff
from multiverse_pipelines.pit.panel import build_panel
from multiverse_pipelines.pit.warehouse import Warehouse
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
        catalog_version="0.11.0",
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
