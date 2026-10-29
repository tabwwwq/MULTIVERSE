"""SEC client, raw archive and connectors against a fake SEC (httpx.MockTransport).

No test reaches the network: a guard makes the real HTTP transport fail. All company data
is synthetic (tests/fixtures/sec/README.md).
"""

import gzip
import io
import os
import zipfile
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_contracts.sources import (
    DataSource,
    DecisionStatus,
    DownloadDecision,
    DownloadScope,
)
from multiverse_pipelines.sec.archive import RawArchive, sha256_file
from multiverse_pipelines.sec.client import SecClient, Validators, parse_retry_after
from multiverse_pipelines.sec.errors import (
    AccessDeniedError,
    ArchiveCorruptedError,
    HostNotAllowedError,
    HttpStatusError,
    RetriesExhaustedError,
    TooLargeError,
)
from multiverse_pipelines.sec.ingest import COMPANYFACTS, SUBMISSIONS, SecIngestor
from multiverse_pipelines.sec.models import FetchRecord, Outcome, RawObject, RunStatus

FIXTURES = Path(__file__).parent / "fixtures" / "sec"
CIK = "0000000001"
SUBMISSIONS_BODY = (FIXTURES / f"submissions-CIK{CIK}.json").read_bytes()
PAGE_BODY = (FIXTURES / f"CIK{CIK}-submissions-001.json").read_bytes()
FACTS_BODY = (FIXTURES / f"companyfacts-CIK{CIK}.json").read_bytes()
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{CIK}.json"
PAGE_URL = f"https://data.sec.gov/submissions/CIK{CIK}-submissions-001.json"
FACTS_URL = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"
BULK_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
AGENT = "MULTIVERSE test tester@example.com"
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
LAST_MODIFIED = "Wed, 28 Oct 2026 03:00:00 GMT"

Reply = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> httpx.Response:
        raise RuntimeError("a test tried to reach the network")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


def streamed(code: int, body: bytes, headers: dict[str, str]) -> httpx.Response:
    # A stream, like the real transport: Response(content=...) would be read in advance,
    # and the bytes on the wire would not be counted.
    return httpx.Response(code, headers=headers, stream=httpx.ByteStream(body))


def ok(body: bytes, **headers: str) -> Reply:
    sent = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "Last-Modified": LAST_MODIFIED,
        **headers,
    }
    return lambda _: streamed(200, body, sent)


def status(code: int, **headers: str) -> Reply:
    return lambda _: httpx.Response(code, headers=headers)


class CutStream(httpx.SyncByteStream):
    """Sends the first bytes, then the connection breaks."""

    def __init__(self, first: bytes) -> None:
        self._first = first

    def __iter__(self) -> Iterator[bytes]:
        yield self._first
        raise httpx.ReadError("connection reset by peer")


def cut(body: bytes) -> Reply:
    headers = {"Content-Length": str(len(body))}
    return lambda _: httpx.Response(200, headers=headers, stream=CutStream(body[:50]))


def short(body: bytes) -> Reply:
    """Content-Length promises more than arrives."""
    headers = {"Content-Length": str(len(body) + 100)}
    return lambda _: streamed(200, body, headers)


class FakeSec:
    """Answers per URL from a queue; the last answer repeats. Records every request."""

    def __init__(self) -> None:
        self.routes: dict[str, list[Reply]] = {}
        self.requests: list[httpx.Request] = []

    def on(self, url: str, *replies: Reply) -> "FakeSec":
        self.routes[url] = list(replies)
        return self

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get(str(request.url))
        if not queue:
            return httpx.Response(404)
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        return reply(request)

    def company(self) -> "FakeSec":
        return (
            self.on(SUBMISSIONS_URL, ok(SUBMISSIONS_BODY))
            .on(PAGE_URL, ok(PAGE_BODY))
            .on(FACTS_URL, ok(FACTS_BODY))
        )


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def sec(scope: DownloadScope = DownloadScope.SAMPLE) -> DataSource:
    source = next(s for s in SOURCE_CATALOG.sources if s.source_id == "sec-edgar")
    if scope is DownloadScope.SAMPLE:
        return source
    decision = DownloadDecision(
        status=DecisionStatus.APPROVED, decided_on=date(2026, 10, 29), scope=scope, note="Test."
    )
    return source.model_copy(update={"download": decision})


@pytest.fixture
def fake() -> FakeSec:
    return FakeSec()


@pytest.fixture
def clock() -> FakeTime:
    return FakeTime()


@pytest.fixture
def archive(tmp_path: Path) -> RawArchive:
    return RawArchive(tmp_path / "raw", budget_bytes=5_000_000)


@pytest.fixture
def client(fake: FakeSec, clock: FakeTime, archive: RawArchive) -> Iterator[SecClient]:
    with SecClient(
        user_agent=AGENT,
        allowed_hosts=("www.sec.gov", "data.sec.gov"),
        rate_per_second=Decimal(2),
        tmp_dir=archive.tmp_dir,
        transport=httpx.MockTransport(fake.handle),
        sleep=clock.sleep,
        clock=clock.clock,
        now=lambda: NOW,
        jitter=lambda: 0.0,
    ) as made:
        yield made


def ingestor(
    client: SecClient,
    archive: RawArchive,
    *,
    at: datetime = NOW,
    run: str = "run-1",
    source: DataSource | None = None,
) -> SecIngestor:
    return SecIngestor(
        client=client,
        archive=archive,
        source=source or sec(),
        catalog_version=SOURCE_CATALOG.contracts_version,
        run_id=run,
        now=lambda: at,
    )


def outcomes(records: tuple[FetchRecord, ...]) -> list[str]:
    return [record.outcome.value for record in records]


# ---------------------------------------------------------------- client


def test_requests_declare_the_user_agent_and_accept_gzip(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    packed = gzip.compress(SUBMISSIONS_BODY)
    fake.on(SUBMISSIONS_URL, ok(packed, **{"Content-Encoding": "gzip"}))
    fetched = client.get(SUBMISSIONS_URL, max_bytes=1_000_000)

    sent = fake.requests[0].headers
    assert sent["User-Agent"] == AGENT
    assert sent["Accept-Encoding"] == "gzip, deflate"
    assert fetched.path is not None
    assert fetched.path.read_bytes() == SUBMISSIONS_BODY  # stored as published, gzip removed
    assert fetched.headers["content-encoding"] == "gzip"
    assert fetched.content_length == len(packed)


def test_requests_are_spaced_by_the_chosen_rate(
    fake: FakeSec, client: SecClient, clock: FakeTime
) -> None:
    fake.company()
    client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    client.get(FACTS_URL, max_bytes=1_000_000)
    client.head(PAGE_URL)
    assert clock.sleeps == [0.5, 0.5]  # 2 requests per second, HEAD included


def test_429_waits_for_retry_after_then_succeeds(
    fake: FakeSec, client: SecClient, clock: FakeTime
) -> None:
    fake.on(SUBMISSIONS_URL, status(429, **{"Retry-After": "30"}), ok(SUBMISSIONS_BODY))
    fetched = client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    assert (fetched.status, fetched.requests) == (200, 2)
    assert clock.sleeps == [30.0]


def test_server_errors_back_off_exponentially_then_give_up(
    fake: FakeSec, client: SecClient, clock: FakeTime
) -> None:
    fake.on(SUBMISSIONS_URL, status(503))
    with pytest.raises(RetriesExhaustedError, match="HTTP 503, 4 requests"):
        client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    assert clock.sleeps == [10.0, 20.0, 40.0]


def test_a_long_retry_after_stops_instead_of_waiting(fake: FakeSec, client: SecClient) -> None:
    fake.on(SUBMISSIONS_URL, status(429, **{"Retry-After": "3600"}))
    with pytest.raises(RetriesExhaustedError, match="Retry-After"):
        client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    assert len(fake.requests) == 1


def test_retry_after_accepts_an_http_date() -> None:
    assert parse_retry_after("Thu, 29 Oct 2026 12:00:45 GMT", NOW) == 45.0
    assert parse_retry_after("soon", NOW) is None


def test_403_stops_at_once(fake: FakeSec, client: SecClient) -> None:
    fake.on(SUBMISSIONS_URL, status(403))
    with pytest.raises(AccessDeniedError, match="User-Agent"):
        client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    assert len(fake.requests) == 1


def test_404_is_not_retried(fake: FakeSec, client: SecClient) -> None:
    with pytest.raises(HttpStatusError, match="HTTP 404"):
        client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    assert len(fake.requests) == 1


def test_a_short_body_is_retried_and_leaves_no_partial_file(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.on(SUBMISSIONS_URL, short(SUBMISSIONS_BODY), ok(SUBMISSIONS_BODY))
    fetched = client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    assert fetched.requests == 2
    assert list(archive.tmp_dir.iterdir()) == [fetched.path]  # only the complete body


def test_an_interrupted_download_is_retried_then_reported(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.on(SUBMISSIONS_URL, cut(SUBMISSIONS_BODY))
    with pytest.raises(RetriesExhaustedError, match="ReadError"):
        client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    assert len(fake.requests) == 4
    assert list(archive.tmp_dir.iterdir()) == []


def test_only_official_hosts_over_https_are_reached(fake: FakeSec, client: SecClient) -> None:
    for url in ("https://example.com/data.json", "http://data.sec.gov/submissions/x.json"):
        with pytest.raises(HostNotAllowedError):
            client.get(url, max_bytes=1)
    redirect = status(302, Location="https://example.com/elsewhere.json")
    fake.on(SUBMISSIONS_URL, redirect)
    with pytest.raises(HostNotAllowedError):
        client.get(SUBMISSIONS_URL, max_bytes=1_000_000)
    assert [str(r.url) for r in fake.requests] == [SUBMISSIONS_URL]


def test_a_body_larger_than_allowed_is_dropped(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.on(SUBMISSIONS_URL, ok(SUBMISSIONS_BODY))
    with pytest.raises(TooLargeError, match="declares"):
        client.get(SUBMISSIONS_URL, max_bytes=100)
    packed = gzip.compress(SUBMISSIONS_BODY)
    fake.on(SUBMISSIONS_URL, ok(packed, **{"Content-Encoding": "gzip"}))
    with pytest.raises(TooLargeError, match="larger than"):
        client.get(SUBMISSIONS_URL, max_bytes=len(packed) + 1)
    assert list(archive.tmp_dir.iterdir()) == []


def test_conditional_headers_come_from_the_archived_copy(fake: FakeSec, client: SecClient) -> None:
    fake.on(SUBMISSIONS_URL, status(304))
    validators = Validators(etag='"abc"', last_modified=LAST_MODIFIED)
    fetched = client.get(SUBMISSIONS_URL, max_bytes=1, validators=validators)
    assert fetched.status == 304
    assert fake.requests[0].headers["If-None-Match"] == '"abc"'
    assert fake.requests[0].headers["If-Modified-Since"] == LAST_MODIFIED


# ---------------------------------------------------------------- archive


def put(archive: RawArchive, body: bytes, *, key: str = f"CIK{CIK}", run: str = "r") -> RawObject:
    archive.tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = archive.tmp_dir / f"{run}-{len(body)}.part"
    tmp.write_bytes(body)

    def describe(sha: str, size: int, path: str) -> RawObject:
        return RawObject(
            source_id="sec-edgar",
            dataset_id=SUBMISSIONS,
            key=key,
            cik=CIK,
            url=SUBMISSIONS_URL,
            path=path,
            sha256=sha,
            size_bytes=size,
            file_format="json",
            content_encoding="identity",
            http_status=200,
            downloaded_at=NOW,
            run_id=run,
            licence="test",
            terms_checked_on=date(2026, 10, 29),
            catalog_version="0.7.0",
        )

    return archive.store(
        tmp, dataset_id=SUBMISSIONS, key=key, file_format="json", describe=describe
    )[0]


def test_stored_files_are_named_by_checksum_and_read_only(archive: RawArchive) -> None:
    row = put(archive, SUBMISSIONS_BODY)
    path = archive.root / row.path
    assert row.path == f"sec/submissions/CIK{CIK}/{row.sha256}.json"
    assert sha256_file(path) == (row.sha256, len(SUBMISSIONS_BODY))
    assert not os.access(path, os.W_OK)
    assert archive.verify().problems == []


def test_the_same_bytes_are_never_stored_twice(archive: RawArchive) -> None:
    first = put(archive, SUBMISSIONS_BODY, run="a")
    again = put(archive, SUBMISSIONS_BODY, run="b")
    assert again == first
    assert len(archive.objects()) == 1
    assert list(archive.tmp_dir.iterdir()) == []


def test_a_changed_file_becomes_a_new_object_next_to_the_old_one(archive: RawArchive) -> None:
    old = put(archive, SUBMISSIONS_BODY, run="a")
    new = put(archive, SUBMISSIONS_BODY.replace(b"SYNF", b"SYNX"), run="b")
    assert old.sha256 != new.sha256
    assert (archive.root / old.path).exists()
    assert len(archive.objects()) == 2


def test_verify_finds_tampered_missing_and_unknown_files(archive: RawArchive) -> None:
    changed = put(archive, SUBMISSIONS_BODY, key="CIK0000000001")
    missing = put(archive, PAGE_BODY, key="CIK0000000002")
    path = archive.root / changed.path
    path.chmod(0o644)
    path.write_bytes(b"{}")
    (archive.root / missing.path).chmod(0o644)
    (archive.root / missing.path).unlink()
    stray = archive.base / "submissions" / "CIK0000000003" / "stray.json"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"{}")

    problems = archive.verify().problems
    assert any(p.startswith("checksum or size changed") for p in problems)
    assert any(p.startswith("writable") for p in problems)
    assert any(p.startswith("missing") for p in problems)
    assert any(p.startswith("not in the index") for p in problems)


def test_a_file_without_its_index_line_is_adopted_after_a_crash(archive: RawArchive) -> None:
    row = put(archive, SUBMISSIONS_BODY)
    archive.index_path.unlink()  # the run stopped after moving the file into place
    again = put(archive, SUBMISSIONS_BODY)
    assert again.sha256 == row.sha256
    assert len(archive.objects()) == 1


def test_a_broken_index_line_is_reported(archive: RawArchive) -> None:
    put(archive, SUBMISSIONS_BODY)
    with archive.index_path.open("a", encoding="utf-8") as handle:
        handle.write('{"sha256": "cut-off\n')
    with pytest.raises(ArchiveCorruptedError, match="line 2"):
        archive.objects()


def test_the_disk_budget_is_enforced(tmp_path: Path) -> None:
    small = RawArchive(tmp_path / "raw", budget_bytes=len(SUBMISSIONS_BODY) + 10)
    put(small, SUBMISSIONS_BODY)
    with pytest.raises(TooLargeError, match="do not fit"):
        put(small, PAGE_BODY, key="CIK0000000002")
    assert list(small.tmp_dir.iterdir()) == []


# ---------------------------------------------------------------- connectors


def test_a_sample_archives_submissions_pages_and_company_facts(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.company()
    manifest = ingestor(client, archive).sample([CIK])

    assert manifest.status is RunStatus.COMPLETED
    assert outcomes(manifest.records) == ["new", "new", "new"]
    assert [r.key for r in manifest.records] == [
        f"CIK{CIK}",
        f"CIK{CIK}/submissions-001",
        f"CIK{CIK}",
    ]
    assert manifest.requests == 3
    rows = {(o.dataset_id, o.key): o for o in archive.objects()}
    facts = rows[(COMPANYFACTS, f"CIK{CIK}")]
    assert (facts.filing_count, facts.latest_filed) == (2, date(2025, 4, 25))
    assert facts.last_modified == LAST_MODIFIED
    assert facts.terms_checked_on == date(2026, 10, 29)
    saved = (archive.runs_dir / "run-1.json").read_text(encoding="utf-8")
    assert "MULTIVERSE_SEC_USER_AGENT" in saved
    assert "@" not in saved  # the contact email stays in .env


def test_a_fresh_archive_answers_without_requests(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.company()
    ingestor(client, archive).sample([CIK])
    later = ingestor(client, archive, at=NOW + timedelta(hours=1), run="run-2").sample([CIK])
    assert outcomes(later.records) == ["fresh_in_archive"] * 3
    assert later.requests == 0


def test_a_stale_copy_is_revalidated_and_304_stores_nothing(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.company()
    ingestor(client, archive).sample([CIK])
    fake.on(SUBMISSIONS_URL, status(304)).on(PAGE_URL, status(304)).on(FACTS_URL, status(304))
    later = ingestor(client, archive, at=NOW + timedelta(days=2), run="run-2").sample([CIK])

    assert outcomes(later.records) == ["not_modified"] * 3
    assert fake.requests[-1].headers["If-Modified-Since"] == LAST_MODIFIED
    assert len(archive.objects()) == 3


def test_a_rerun_with_identical_bytes_creates_no_duplicate(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.company()
    ingestor(client, archive).sample([CIK])
    later = ingestor(client, archive, at=NOW + timedelta(days=2), run="run-2").sample([CIK])
    assert outcomes(later.records) == ["unchanged"] * 3
    assert len(archive.objects()) == 3


def test_a_response_older_than_the_archived_copy_is_not_stored(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.company()
    ingestor(client, archive).sample([CIK])
    older = SUBMISSIONS_BODY.replace(b"SYNF", b"SYNO")
    fake.on(SUBMISSIONS_URL, ok(older, **{"Last-Modified": "Mon, 26 Oct 2026 03:00:00 GMT"}))
    later = ingestor(client, archive, at=NOW + timedelta(days=2), run="run-2").sample([CIK])

    assert later.records[0].outcome is Outcome.STALE_RESPONSE
    assert len([o for o in archive.objects() if o.key == f"CIK{CIK}"]) == 2  # facts + old one


def test_a_corrupted_file_fails_alone_and_the_run_continues(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.company().on(FACTS_URL, ok(FACTS_BODY[:200]))
    manifest = ingestor(client, archive).sample([CIK])
    assert manifest.status is RunStatus.FAILED
    assert outcomes(manifest.records) == ["new", "new", "failed"]
    assert "not valid JSON" in (manifest.records[2].error or "")
    assert {o.dataset_id for o in archive.objects()} == {SUBMISSIONS}
    assert list(archive.tmp_dir.iterdir()) == []


def test_429_inside_a_run_is_recorded_with_its_extra_request(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.company().on(FACTS_URL, status(429, **{"Retry-After": "1"}), ok(FACTS_BODY))
    manifest = ingestor(client, archive).sample([CIK])
    assert manifest.status is RunStatus.COMPLETED
    assert manifest.records[2].requests == 2


def test_403_aborts_the_whole_run(fake: FakeSec, client: SecClient, archive: RawArchive) -> None:
    fake.company().on(SUBMISSIONS_URL, status(403))
    manifest = ingestor(client, archive).sample([CIK, "0000000002"])
    assert manifest.status is RunStatus.ABORTED
    assert "403" in (manifest.message or "")
    assert len(fake.requests) == 1  # nothing after the refusal
    assert (archive.runs_dir / "run-1.json").exists()


def test_partials_of_an_interrupted_run_are_removed_at_the_next_start(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    archive.tmp_dir.mkdir(parents=True)
    (archive.tmp_dir / "killed.part").write_bytes(b'{"cik": "1", "na')
    fake.company()
    ingestor(client, archive).sample([CIK])
    assert list(archive.tmp_dir.iterdir()) == []


def test_running_out_of_budget_aborts(fake: FakeSec, client: SecClient, tmp_path: Path) -> None:
    small = RawArchive(tmp_path / "small", budget_bytes=len(SUBMISSIONS_BODY) + 10)
    fake.company()
    manifest = ingestor(client, small).sample([CIK])
    assert manifest.status is RunStatus.ABORTED
    assert outcomes(manifest.records) == ["new"]


def zip_body(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_probe_reads_the_size_with_one_head_request(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.on(
        BULK_URL, status(200, **{"Content-Length": "1395864576", "Last-Modified": LAST_MODIFIED})
    )
    run = ingestor(client, archive)
    manifest = run.probe(run.connectors.bulk("companyfacts-zip"))
    [record] = manifest.records
    assert (record.outcome, record.content_length) == (Outcome.PROBED, 1395864576)
    assert [r.method for r in fake.requests] == ["HEAD"]
    assert archive.objects() == []


def test_bulk_refuses_a_file_larger_than_allowed_before_downloading(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    fake.on(BULK_URL, status(200, **{"Content-Length": "1395864576"}))
    run = ingestor(client, archive, source=sec(DownloadScope.BULK))
    manifest = run.bulk(run.connectors.bulk("companyfacts-zip"), max_bytes=10_000_000)
    assert manifest.status is RunStatus.ABORTED
    assert [r.method for r in fake.requests] == ["HEAD"]


def test_bulk_stores_a_valid_zip_and_rejects_a_corrupted_one(
    fake: FakeSec, client: SecClient, archive: RawArchive
) -> None:
    body = zip_body({f"CIK{CIK}.json": FACTS_BODY})
    sized = {"Content-Length": str(len(body))}
    fake.on(
        BULK_URL,
        lambda r: streamed(200, body if r.method == "GET" else b"", sized),
    )
    run = ingestor(client, archive, source=sec(DownloadScope.BULK))
    manifest = run.bulk(run.connectors.bulk("companyfacts-zip"), max_bytes=10_000_000)
    assert outcomes(manifest.records) == ["probed", "new"]
    [row] = archive.objects()
    assert (row.key, row.file_format) == ("bulk/companyfacts", "zip")

    broken = bytearray(body)
    broken[40] ^= 0xFF
    fake.on(
        BULK_URL,
        lambda r: streamed(200, bytes(broken) if r.method == "GET" else b"", sized),
    )
    later = ingestor(
        client, archive, at=NOW + timedelta(days=2), run="run-2", source=sec(DownloadScope.BULK)
    )
    manifest = later.bulk(later.connectors.bulk("companyfacts-zip"), max_bytes=10_000_000)
    assert manifest.status is RunStatus.FAILED
    assert len(archive.objects()) == 1
