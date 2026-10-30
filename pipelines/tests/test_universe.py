"""The study universe drawn from the bulk files (decision D-10). Every company is invented.

Two small ZIP files stand in for companyfacts.zip and submissions.zip; nothing is
downloaded.
"""

import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_pipelines.pit.build import archived_files, observed_at, read_inputs
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.sec.universe import (
    RULES,
    Scanned,
    allocate,
    division,
    eligibility,
    excluded_ranges,
    extract,
    manifest,
    scan,
    select,
)

DOWNLOADED = datetime(2026, 10, 30, 11, 48, tzinfo=UTC)
BUILT_BY_SEC = "Fri, 30 Oct 2026 04:25:37 GMT"
EXCLUDED = excluded_ranges(SOURCE_CATALOG.sectors)


def facts(cik: str, concept: str) -> dict[str, Any]:
    value = {"end": "2020-12-31", "start": "2020-01-01", "val": 100, "accn": "0000000000-21-000001"}
    value |= {"fy": 2020, "fp": "FY", "form": "10-K", "filed": "2021-02-01"}
    return {
        "cik": int(cik),
        "entityName": f"Company {cik}",
        "facts": {"us-gaap": {concept: {"label": concept, "units": {"USD": [value]}}}},
    }


def table(forms: list[str], start: int = 2010) -> dict[str, list[Any]]:
    days = [f"{start + i // 4}-{3 * (i % 4) + 2:02d}-10" for i in range(len(forms))]
    return {
        "accessionNumber": [f"0000000000-{i:02d}-000001" for i in range(len(forms))],
        "filingDate": days,
        "acceptanceDateTime": [f"{d}T20:00:00.000Z" for d in days],
        "form": forms,
        "isXBRL": [1] * len(forms),
        "reportDate": [""] * len(forms),
    }


REPORTS = (["10-Q"] * 3 + ["10-K"]) * 4  # four years of reports


def submissions(cik: str, sic: str, forms: list[str], pages: int = 0) -> dict[str, Any]:
    return {
        "cik": cik,
        "name": f"Company {cik}",
        "sic": sic,
        "filings": {
            "recent": table(forms),
            "files": [
                {"name": f"CIK{cik}-submissions-{n:03d}.json", "filingCount": 1}
                for n in range(1, pages + 1)
            ],
        },
    }


COMPANIES: dict[str, tuple[str, str | None, list[str]]] = {
    # cik: (sic, revenue concept or None, forms)
    "0000000001": ("3674", "Revenues", REPORTS),
    "0000000002": ("3841", None, REPORTS),  # no revenue concept
    "0000000003": ("6022", "Revenues", REPORTS),  # a bank: excluded sector
    "0000000004": ("7372", "Revenues", REPORTS[:8]),  # two years of reports only
    "0000000005": ("4911", "SalesRevenueNet", [*REPORTS, "15-12B"]),  # deregistered
    "0000000006": ("7372", "RevenueFromContractWithCustomerExcludingAssessedTax", REPORTS),
    "0000000007": ("2834", "Revenues", [*REPORTS[:4], "15-12G", *REPORTS[4:]]),  # still reports
    "0000000008": ("1311", "Revenues", ["10-Q"] * 16),  # no 10-K
}


def write_zips(folder: Path) -> tuple[Path, Path]:
    facts_zip, submissions_zip = folder / "companyfacts.zip", folder / "submissions.zip"
    with zipfile.ZipFile(facts_zip, "w") as f, zipfile.ZipFile(submissions_zip, "w") as s:
        for cik, (sic, concept, forms) in COMPANIES.items():
            f.writestr(f"CIK{cik}.json", json.dumps(facts(cik, concept or "Assets")))
            pages = 1 if cik == "0000000001" else 0
            s.writestr(f"CIK{cik}.json", json.dumps(submissions(cik, sic, forms, pages)))
        s.writestr("CIK0000000001-submissions-001.json", json.dumps(table(["8-K"], 2005)))
        f.writestr("CIK0000000009.json", json.dumps(facts("0000000009", "Revenues")))
    return facts_zip, submissions_zip


def test_the_rules_leave_the_eligible_companies(tmp_path: Path) -> None:
    scanned = scan(*write_zips(tmp_path), EXCLUDED)
    assert [c.cik for c in scanned][-1] == "0000000009"
    rules, eligible = eligibility(scanned, EXCLUDED)
    assert [r.rule for r in rules] == list(RULES)
    assert [r.remaining for r in rules] == [8, 6, 5, 4]
    assert [c.cik for c in eligible] == ["0000000001", "0000000005", "0000000006", "0000000007"]
    by_cik = {c.cik: c for c in scanned}
    assert by_cik["0000000005"].deregistered
    assert not by_cik["0000000007"].deregistered  # a periodic report after the Form 15
    assert by_cik["0000000001"].last_filed == date(2013, 11, 10)
    assert by_cik["0000000001"].first_xbrl_filed == date(2010, 2, 10)
    assert by_cik["0000000002"].revenue is False
    assert by_cik["0000000003"].revenue is None  # left out before the revenue rule


def test_shares_follow_the_eligible_counts_by_largest_remainder() -> None:
    assert allocate({"D": 3236, "I": 1829, "A": 61}, 100) == {"D": 63, "I": 36, "A": 1}
    assert sum(allocate({"A": 1, "B": 1, "C": 1}, 2).values()) == 2
    with pytest.raises(ValueError, match="needs more"):
        allocate({"A": 1}, 2)
    assert division("3674") == ("D", "Manufacturing")
    assert division("9995")[0] == "K"


def company(cik: str, sic: str) -> Scanned:
    return Scanned(
        cik, f"C{cik}", sic, 4, 12, date(2010, 1, 1), date(2020, 1, 1), False, True, True
    )


def test_the_draw_is_seeded_and_keeps_the_required_companies() -> None:
    pool = [company(f"{n:010d}", "3674" if n % 3 else "7372") for n in range(1, 61)]
    strata, chosen = select(pool, 12, 7, required=["0000000004"])
    again = select(pool, 12, 7, required=["0000000004"])[1]
    assert [c.cik for c in chosen] == [c.cik for c in again]
    assert "0000000004" in {c.cik for c in chosen}
    assert {s.division: s.selected for s in strata} == {"D": 8, "I": 4}
    other = select(pool, 12, 8, required=["0000000004"])[1]
    assert [c.cik for c in other] != [c.cik for c in chosen]
    with pytest.raises(ValueError, match="not eligible"):
        select(pool, 12, 7, required=["0000000099"])


def zip_row(dataset: str, key: str, path: Path, root: Path) -> RawObject:
    return RawObject(
        source_id="sec-edgar",
        dataset_id=dataset,
        key=key,
        url=f"https://www.sec.gov/fixture/{path.name}",
        path=path.relative_to(root).as_posix(),
        sha256="0" * 64,
        size_bytes=path.stat().st_size,
        file_format="zip",
        content_encoding="identity",
        http_status=200,
        last_modified=BUILT_BY_SEC,
        downloaded_at=DOWNLOADED,
        run_id="fixture",
        licence="fixture",
        terms_checked_on=date(2026, 10, 29),
        catalog_version="0.13.0",
    )


def test_files_are_copied_out_byte_for_byte_and_named_by_member(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    (root / "sec").mkdir(parents=True)
    facts_zip, submissions_zip = write_zips(root / "sec")
    archive = RawArchive(root, budget_bytes=10_000_000)
    facts_row = zip_row("sec-companyfacts", "bulk/companyfacts", facts_zip, root)
    submissions_row = zip_row("sec-submissions", "bulk/submissions", submissions_zip, root)
    report = extract(archive, ["0000000001"], facts_row, submissions_row, run_id="t")
    assert (report.stored, report.unchanged) == (3, 0)
    again = extract(archive, ["0000000001"], facts_row, submissions_row, run_id="t")
    assert (again.stored, again.unchanged) == (0, 3)
    rows = {row.key: row for row in archive.objects()}
    assert set(rows) == {"CIK0000000001", "CIK0000000001/submissions-001"}
    page = rows["CIK0000000001/submissions-001"]
    assert page.url.endswith("submissions.zip#CIK0000000001-submissions-001.json")
    with zipfile.ZipFile(submissions_zip) as source:
        member = source.read("CIK0000000001-submissions-001.json")
    assert (root / page.path).read_bytes() == member
    files = archived_files(archive)("0000000001")
    assert files.facts.dataset_id == "sec-companyfacts"
    assert [p.key for p in files.pages] == ["CIK0000000001/submissions-001"]
    # The ZIP was built hours before the download: its content is as of the build.
    assert observed_at(files.submissions) == datetime(2026, 10, 30, 4, 25, 37, tzinfo=UTC)
    assert read_inputs(files).observed_at == observed_at(files.submissions)
    # Only the two fixture ZIP files, placed without an index line, are unknown to it.
    assert [p.rsplit("/", 1)[-1] for p in archive.verify().problems] == [
        "companyfacts.zip",
        "submissions.zip",
    ]


def test_the_manifest_states_rules_strata_and_sources(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    (root / "sec").mkdir(parents=True)
    facts_zip, submissions_zip = write_zips(root / "sec")
    scanned = scan(facts_zip, submissions_zip, EXCLUDED)
    rules, eligible = eligibility(scanned, EXCLUDED)
    strata, chosen = select(eligible, 3, 20261030, required=["0000000005"])
    universe = manifest(
        universe_id="sec-3-20261030",
        seed=20261030,
        size=3,
        created_at=DOWNLOADED,
        sources=(
            zip_row("sec-companyfacts", "bulk/companyfacts", facts_zip, root),
            zip_row("sec-submissions", "bulk/submissions", submissions_zip, root),
        ),
        scanned=len(scanned),
        rules=rules,
        strata=strata,
        chosen=chosen,
        required=["0000000005"],
    )
    assert len(universe.companies) == 3
    assert [c.cik for c in universe.companies if c.candidate] == ["0000000005"]
    assert next(c for c in universe.companies if c.cik == "0000000005").deregistered
    assert sum(s.eligible for s in universe.strata) == 4
