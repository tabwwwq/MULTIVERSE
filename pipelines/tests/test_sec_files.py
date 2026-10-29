"""SEC files without the network: CIKs, structural checks, the download locks, coverage, CLI.

All company data here is synthetic (tests/fixtures/sec/README.md).
"""

import io
import json
import os
import shutil
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from multiverse_config import Settings
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_contracts.sources import (
    DataSource,
    DecisionStatus,
    DownloadDecision,
    DownloadScope,
)
from multiverse_pipelines.sec import cli
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.cik import cik10, cik_int
from multiverse_pipelines.sec.coverage import build_coverage, to_markdown
from multiverse_pipelines.sec.errors import InvalidPayloadError, PermissionRefusedError
from multiverse_pipelines.sec.gate import check_user_agent, require_permission
from multiverse_pipelines.sec.ingest import COMPANYFACTS, FSDS, SUBMISSIONS, Connectors
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.sec.validate import (
    FSDS_MEMBERS,
    check_companyfacts,
    check_submissions,
    check_submissions_page,
    check_zip,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sec"
CIK = "0000000001"
SUBMISSIONS_FILE = FIXTURES / f"submissions-CIK{CIK}.json"
PAGE_FILE = FIXTURES / f"CIK{CIK}-submissions-001.json"
FACTS_FILE = FIXTURES / f"companyfacts-CIK{CIK}.json"
AGENT = "MULTIVERSE test tester@example.com"


def sec() -> DataSource:
    return next(s for s in SOURCE_CATALOG.sources if s.source_id == "sec-edgar")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith("MULTIVERSE_"):
            monkeypatch.delenv(name)
    # The CLI reads .env and var/raw relative to the working directory: keep both empty.
    monkeypatch.chdir(tmp_path)


def settings(**values: object) -> Settings:
    return Settings.model_validate(values)


def write_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


# ---------------------------------------------------------------- CIK


@pytest.mark.parametrize("value", ["97476", 97476, "0000097476", "CIK0000097476", " cik97476 "])
def test_cik_is_padded_to_ten_digits(value: str | int) -> None:
    assert cik10(value) == "0000097476"
    assert cik_int(value) == 97476


@pytest.mark.parametrize("value", ["", "0", "abc", "12345678901", "-5", "97476.0"])
def test_a_malformed_cik_is_refused(value: str) -> None:
    with pytest.raises(ValueError, match="not a CIK"):
        cik10(value)


def test_addresses_follow_the_catalog_patterns() -> None:
    connectors = Connectors(sec())
    assert (
        connectors.submissions("97476").url == "https://data.sec.gov/submissions/CIK0000097476.json"
    )
    facts = connectors.companyfacts("97476").url
    assert facts == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000097476.json"
    page = connectors.submissions_page("97476", "CIK0000097476-submissions-001.json")
    assert page.url == "https://data.sec.gov/submissions/CIK0000097476-submissions-001.json"
    assert page.key == "CIK0000097476/submissions-001"
    fsds = connectors.bulk("fsds", "2024q1")
    assert fsds.url.endswith("/financial-statement-data-sets/2024q1.zip")
    assert fsds.dataset_id == FSDS


def test_a_page_of_another_company_or_a_bad_quarter_is_refused() -> None:
    connectors = Connectors(sec())
    with pytest.raises(InvalidPayloadError):
        connectors.submissions_page("97476", "CIK0000000002-submissions-001.json")
    with pytest.raises(InvalidPayloadError):
        connectors.submissions_page("97476", "../../etc/passwd")
    with pytest.raises(ValueError, match="2024q1"):
        connectors.bulk("fsds", "2024Q5")


# ---------------------------------------------------------------- structural checks


def test_submissions_fixture_passes_with_its_filing_summary() -> None:
    summary = check_submissions(SUBMISSIONS_FILE, CIK)
    assert summary.filing_count == 5
    assert summary.latest_filing_id == "0000000001-25-000003"
    assert summary.latest_filed == date(2025, 4, 25)
    assert summary.pages == ("CIK0000000001-submissions-001.json",)
    assert check_submissions_page(PAGE_FILE).filing_count == 2


def test_companyfacts_fixture_counts_distinct_filings() -> None:
    summary = check_companyfacts(FACTS_FILE, CIK)
    assert summary.filing_count == 2
    assert summary.latest_filing_id == "0000000001-25-000003"


def test_a_file_of_another_company_is_refused() -> None:
    with pytest.raises(InvalidPayloadError, match="expected 0000000002"):
        check_submissions(SUBMISSIONS_FILE, "2")
    with pytest.raises(InvalidPayloadError, match="CIK"):
        check_companyfacts(FACTS_FILE, "2")


def test_a_partial_json_response_is_refused(tmp_path: Path) -> None:
    cut = tmp_path / "cut.json"
    cut.write_bytes(SUBMISSIONS_FILE.read_bytes()[:300])
    with pytest.raises(InvalidPayloadError, match="not valid JSON"):
        check_submissions(cut, CIK)


def test_filing_columns_of_unequal_length_are_refused(tmp_path: Path) -> None:
    doc = json.loads(SUBMISSIONS_FILE.read_text(encoding="utf-8"))
    doc["filings"]["recent"]["form"].pop()
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(InvalidPayloadError, match="different lengths"):
        check_submissions(broken, CIK)


def test_a_fact_without_its_filing_is_refused(tmp_path: Path) -> None:
    doc = json.loads(FACTS_FILE.read_text(encoding="utf-8"))
    del doc["facts"]["us-gaap"]["ResearchAndDevelopmentExpense"]["units"]["USD"][0]["accn"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(InvalidPayloadError, match="lacks accn"):
        check_companyfacts(broken, CIK)


def test_a_complete_zip_passes(tmp_path: Path) -> None:
    members = {name: b"adsh\ttag\n" * 50 for name in FSDS_MEMBERS}
    check_zip(write_zip(tmp_path / "2024q1.zip", members), FSDS_MEMBERS)


def test_a_corrupted_zip_fails_its_crc_check(tmp_path: Path) -> None:
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("sub.txt", b"0123456789" * 200)
    with zipfile.ZipFile(path) as archive:
        info = archive.infolist()[0]
    data = bytearray(path.read_bytes())
    data[info.header_offset + 30 + len(info.filename) + len(info.extra) + 5] ^= 0xFF
    path.write_bytes(bytes(data))
    with pytest.raises(InvalidPayloadError, match="CRC"):
        check_zip(path)


def test_a_truncated_or_foreign_zip_is_refused(tmp_path: Path) -> None:
    path = write_zip(tmp_path / "ok.zip", {"sub.txt": b"x" * 1000})
    cut = tmp_path / "cut.zip"
    cut.write_bytes(path.read_bytes()[:-40])
    with pytest.raises(InvalidPayloadError, match="not a readable ZIP"):
        check_zip(cut)
    html = tmp_path / "page.zip"
    html.write_bytes(b"<html>Request rate threshold exceeded</html>")
    with pytest.raises(InvalidPayloadError, match="not a readable ZIP"):
        check_zip(html)
    with pytest.raises(InvalidPayloadError, match=r"lacks num\.txt"):
        check_zip(path, FSDS_MEMBERS)


# ---------------------------------------------------------------- the three locks


def test_downloads_are_refused_while_the_switch_is_off() -> None:
    with pytest.raises(PermissionRefusedError, match="ALLOW_NETWORK_DOWNLOADS"):
        require_permission(settings(sec_user_agent=AGENT), sec(), DownloadScope.SAMPLE)


@pytest.mark.parametrize("agent", ["tester@example.com", "MULTIVERSE research", "MULTIVERSE @"])
def test_a_user_agent_needs_a_name_and_an_email(agent: str) -> None:
    with pytest.raises(PermissionRefusedError, match="contact email"):
        check_user_agent(agent)


def test_a_source_without_the_owners_approval_is_refused() -> None:
    fred = next(s for s in SOURCE_CATALOG.sources if s.source_id == "fred-alfred")
    allowed = settings(allow_network_downloads=True, sec_user_agent=AGENT)
    with pytest.raises(PermissionRefusedError, match="not approved"):
        require_permission(allowed, fred, DownloadScope.SAMPLE)


def test_a_sample_approval_does_not_open_bulk_files() -> None:
    allowed = settings(allow_network_downloads=True, sec_user_agent=AGENT)
    assert require_permission(allowed, sec(), DownloadScope.SAMPLE) == AGENT
    with pytest.raises(PermissionRefusedError, match="D-10"):
        require_permission(allowed, sec(), DownloadScope.BULK)
    bulk = sec().model_copy(
        update={
            "download": DownloadDecision(
                status=DecisionStatus.APPROVED,
                decided_on=date(2026, 10, 29),
                scope=DownloadScope.BULK,
                note="Test only.",
            )
        }
    )
    assert require_permission(allowed, bulk, DownloadScope.BULK) == AGENT


# ---------------------------------------------------------------- coverage


def archive_fixtures(archive: RawArchive) -> None:
    """Put the synthetic files into an archive the way a sample run would."""
    files = [
        (SUBMISSIONS, f"CIK{CIK}", SUBMISSIONS_FILE),
        (SUBMISSIONS, f"CIK{CIK}/submissions-001", PAGE_FILE),
        (COMPANYFACTS, f"CIK{CIK}", FACTS_FILE),
    ]
    archive.tmp_dir.mkdir(parents=True, exist_ok=True)
    for dataset_id, key, source in files:
        tmp = archive.tmp_dir / f"{source.name}.part"
        shutil.copyfile(source, tmp)

        def describe(
            sha: str, size: int, path: str, dataset_id: str = dataset_id, key: str = key
        ) -> RawObject:
            return RawObject(
                source_id="sec-edgar",
                dataset_id=dataset_id,
                key=key,
                cik=CIK,
                url="https://data.sec.gov/fixture",
                path=path,
                sha256=sha,
                size_bytes=size,
                file_format="json",
                content_encoding="identity",
                http_status=200,
                downloaded_at=datetime(2026, 10, 29, tzinfo=UTC),
                run_id="fixture",
                licence="fixture",
                terms_checked_on=date(2026, 10, 29),
                catalog_version="0.7.0",
            )

        archive.store(tmp, dataset_id=dataset_id, key=key, file_format="json", describe=describe)


def test_coverage_counts_filings_taxonomies_and_metric_periods(tmp_path: Path) -> None:
    archive = RawArchive(tmp_path / "raw", budget_bytes=10_000_000)
    archive_fixtures(archive)
    synthetic = SOURCE_CATALOG.candidates[0].model_copy(update={"cik": CIK, "name": "Synthetic"})
    [row] = build_coverage(archive, [synthetic])

    assert row.found
    assert (row.sic_matches, row.fiscal_year_end_matches) == (True, True)
    assert (row.filings, row.pages_listed, row.pages_archived) == (5, 1, 1)
    assert row.forms == {"10-K": 1, "10-Q": 3}
    assert row.first_filed == date(2009, 4, 30)
    assert row.facts_by_taxonomy == {"dei": 1, "us-gaap": 3}
    revenue = row.metrics["revenue"]
    assert revenue.concepts == ("RevenueFromContractWithCustomerExcludingAssessedTax",)
    assert (revenue.periods, revenue.last_end) == (2, date(2025, 3, 31))
    assert row.metrics["capex"].periods == 0
    table = to_markdown([row])
    assert "| 1 | Synthetic | yes | 5 | 1 | 3 |" in table
    assert "2 (2024-2025)" in table


def test_a_company_not_yet_archived_is_reported_as_such(tmp_path: Path) -> None:
    rows = build_coverage(RawArchive(tmp_path, budget_bytes=1), SOURCE_CATALOG.candidates[:2])
    assert [row.found for row in rows] == [False, False]
    assert "not archived" in to_markdown(rows)


# ---------------------------------------------------------------- CLI


def test_status_works_offline(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "network downloads   off" in out
    assert "approved (sample)" in out
    assert "@" not in out


def test_sample_is_refused_without_the_switch(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["sample", "--cik", "97476"]) == 2
    assert "MULTIVERSE_ALLOW_NETWORK_DOWNLOADS" in capsys.readouterr().err
    assert not Path("var").exists()


def test_bulk_is_refused_with_a_sample_approval(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MULTIVERSE_ALLOW_NETWORK_DOWNLOADS", "true")
    monkeypatch.setenv("MULTIVERSE_SEC_USER_AGENT", AGENT)
    assert cli.main(["bulk", "companyfacts-zip", "--max-mb", "1"]) == 2
    assert "D-10" in capsys.readouterr().err


def test_verify_and_coverage_work_on_an_empty_archive(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["verify"]) == 0
    assert cli.main(["coverage", "--json"]) == 0
    out = capsys.readouterr().out
    assert "0 files checked, 0 problems" in out
    assert json.load(io.StringIO(out[out.index("[") :]))[0]["found"] is False


def test_probe_and_sample_run_through_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MULTIVERSE_ALLOW_NETWORK_DOWNLOADS", "true")
    monkeypatch.setenv("MULTIVERSE_SEC_USER_AGENT", AGENT)
    bodies = {
        f"/submissions/CIK{CIK}.json": SUBMISSIONS_FILE.read_bytes(),
        f"/submissions/CIK{CIK}-submissions-001.json": PAGE_FILE.read_bytes(),
        f"/api/xbrl/companyfacts/CIK{CIK}.json": FACTS_FILE.read_bytes(),
    }

    def answer(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == AGENT
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "123456789"})
        body = bodies[request.url.path]
        return httpx.Response(
            200, headers={"Content-Length": str(len(body))}, stream=httpx.ByteStream(body)
        )

    transport = httpx.MockTransport(answer)
    assert cli.main(["probe", "companyfacts-zip"], transport=transport) == 0
    assert cli.main(["sample", "--cik", "1"], transport=transport) == 0
    out = capsys.readouterr().out
    assert "probed" in out
    assert "117.7 MB" in out
    assert out.count("new ") == 3
    assert cli.main(["verify"]) == 0
