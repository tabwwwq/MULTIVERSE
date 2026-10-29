"""Raw connectors for the Submissions API, the Company Facts API and the bulk ZIP files.

``sample`` fetches named companies through the API: submissions with the older-filing
pages they list, then company facts. ``bulk`` fetches one bulk ZIP after a HEAD request
has shown that it fits; only the explicit ``bulk`` command reaches it (ADR-0017).
Addresses come from the dataset patterns of the source catalog.
"""

import email.utils
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from multiverse_contracts.sources import DataSource
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.cik import cik10
from multiverse_pipelines.sec.client import SecClient, Validators
from multiverse_pipelines.sec.errors import (
    AccessDeniedError,
    ArchiveCorruptedError,
    HostNotAllowedError,
    HttpStatusError,
    IngestionError,
    InvalidPayloadError,
    RetriesExhaustedError,
    TooLargeError,
)
from multiverse_pipelines.sec.models import (
    FetchRecord,
    Outcome,
    RawObject,
    RunManifest,
    RunStatus,
)
from multiverse_pipelines.sec.validate import (
    FSDS_MEMBERS,
    Summary,
    check_companyfacts,
    check_submissions,
    check_submissions_page,
    check_zip,
)

SUBMISSIONS = "sec-submissions"
COMPANYFACTS = "sec-companyfacts"
FSDS = "sec-financial-statement-data-sets"
BULK_TARGETS = ("companyfacts-zip", "submissions-zip", "fsds")
_PAGE = re.compile(r"^CIK(\d{10})-submissions-(\d{3})\.json$")
_QUARTER = re.compile(r"^(\d{4})q([1-4])$")


@dataclass(frozen=True)
class Target:
    dataset_id: str
    key: str
    url: str
    file_format: Literal["json", "zip"]
    check: Callable[[Path], Summary]
    cik: str | None = None


def endpoint(source: DataSource, dataset_id: str, suffix: str) -> str:
    dataset = next(d for d in source.datasets if d.dataset_id == dataset_id)
    return next(e for e in dataset.endpoints if e.endswith(suffix))


class Connectors:
    """One target per raw file, built from the catalog's address patterns."""

    def __init__(self, source: DataSource) -> None:
        self._source = source

    def submissions(self, cik: str) -> Target:
        c = cik10(cik)
        url = endpoint(self._source, SUBMISSIONS, "CIK{cik10}.json").format(cik10=c)
        return Target(SUBMISSIONS, f"CIK{c}", url, "json", lambda p: check_submissions(p, c), c)

    def submissions_page(self, cik: str, name: str) -> Target:
        c = cik10(cik)
        match = _PAGE.fullmatch(name)
        if match is None or match[1] != c:
            raise InvalidPayloadError(f"unexpected older-filing page {name!r} for CIK {c}")
        base = self.submissions(c).url.rsplit("/", 1)[0]
        key = f"CIK{c}/submissions-{match[2]}"
        return Target(SUBMISSIONS, key, f"{base}/{name}", "json", check_submissions_page, c)

    def companyfacts(self, cik: str) -> Target:
        c = cik10(cik)
        url = endpoint(self._source, COMPANYFACTS, "CIK{cik10}.json").format(cik10=c)
        return Target(COMPANYFACTS, f"CIK{c}", url, "json", lambda p: check_companyfacts(p, c), c)

    def bulk(self, name: str, quarter: str | None = None) -> Target:
        if name == "companyfacts-zip":
            url = endpoint(self._source, COMPANYFACTS, "companyfacts.zip")
            return Target(COMPANYFACTS, "bulk/companyfacts", url, "zip", check_zip)
        if name == "submissions-zip":
            url = endpoint(self._source, SUBMISSIONS, "submissions.zip")
            return Target(SUBMISSIONS, "bulk/submissions", url, "zip", check_zip)
        if name == "fsds":
            match = _QUARTER.fullmatch(quarter or "")
            if match is None:
                raise ValueError("fsds needs --quarter in the form 2024q1")
            pattern = endpoint(self._source, FSDS, "{yyyy}q{q}.zip")
            url = pattern.format(yyyy=match[1], q=match[2])
            return Target(FSDS, f"{match[1]}q{match[2]}", url, "zip", _check_fsds)
        raise ValueError(f"unknown bulk target {name!r}; use one of {', '.join(BULK_TARGETS)}")


def _check_fsds(path: Path) -> Summary:
    return check_zip(path, FSDS_MEMBERS)


def _http_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _older(received: str | None, archived: str | None) -> bool:
    new, old = _http_date(received), _http_date(archived)
    return new is not None and old is not None and new < old


class SecIngestor:
    def __init__(
        self,
        *,
        client: SecClient,
        archive: RawArchive,
        source: DataSource,
        catalog_version: str,
        run_id: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_age: timedelta = timedelta(hours=12),
    ) -> None:
        self.client = client
        self.archive = archive
        self.source = source
        self.connectors = Connectors(source)
        self._catalog_version = catalog_version
        self._run_id = run_id
        self._now = now
        self._max_age = max_age
        self._checked = archive.last_checked()

    def sample(self, ciks: Sequence[str]) -> RunManifest:
        def body(records: list[FetchRecord]) -> None:
            for cik in ciks:
                main = self.connectors.submissions(cik)
                record, path = self._fetch(main)
                records.append(record)
                if path is not None:
                    for name in check_submissions(path, cik).pages:
                        try:
                            page = self.connectors.submissions_page(cik, name)
                        except InvalidPayloadError as exc:
                            records.append(self._failed(main, str(exc)))
                            continue
                        records.append(self._fetch(page)[0])
                records.append(self._fetch(self.connectors.companyfacts(cik))[0])

        return self._run("sample", body)

    def probe(self, target: Target) -> RunManifest:
        return self._run("probe", lambda records: records.append(self._head(target)))

    def bulk(self, target: Target, *, max_bytes: int) -> RunManifest:
        def body(records: list[FetchRecord]) -> None:
            probe = self._head(target)
            records.append(probe)
            limit = min(max_bytes, self.archive.remaining_bytes())
            if probe.content_length is None or probe.content_length > limit:
                raise TooLargeError(
                    f"{target.url} has {probe.content_length or 'an unknown number of'} bytes; "
                    f"{limit} allowed by --max-mb and the disk budget"
                )
            records.append(self._fetch(target, max_bytes=limit)[0])

        return self._run("bulk", body)

    def _failed(self, target: Target, error: str) -> FetchRecord:
        return FetchRecord(
            dataset_id=target.dataset_id,
            key=target.key,
            url=target.url,
            outcome=Outcome.FAILED,
            requests=0,
            checked_at=self._now(),
            error=error,
        )

    def _head(self, target: Target) -> FetchRecord:
        before = self.client.requests_made
        fetched = self.client.head(target.url)
        return FetchRecord(
            dataset_id=target.dataset_id,
            key=target.key,
            url=target.url,
            outcome=Outcome.PROBED,
            requests=self.client.requests_made - before,
            checked_at=self._now(),
            content_length=fetched.content_length,
            last_modified=fetched.headers.get("last-modified"),
        )

    def _run(
        self, mode: Literal["sample", "probe", "bulk"], body: Callable[[list[FetchRecord]], None]
    ) -> RunManifest:
        started = self._now()
        self.archive.clean_partials()
        records: list[FetchRecord] = []
        status, message = RunStatus.COMPLETED, None
        try:
            body(records)
        except (
            AccessDeniedError,
            TooLargeError,
            HostNotAllowedError,
            ArchiveCorruptedError,
        ) as exc:
            status, message = RunStatus.ABORTED, str(exc)
        except IngestionError as exc:
            status, message = RunStatus.FAILED, str(exc)
        failed = sum(r.outcome is Outcome.FAILED for r in records)
        if status is RunStatus.COMPLETED and failed:
            status, message = RunStatus.FAILED, f"{failed} of {len(records)} files failed"
        decision = self.source.download
        manifest = RunManifest(
            run_id=self._run_id,
            mode=mode,
            started_at=started,
            finished_at=self._now(),
            status=status,
            message=message,
            rate_per_second=self.source.rate_limit.chosen_requests_per_second,
            catalog_version=self._catalog_version,
            decision_status=decision.status,
            decision_scope=decision.scope,
            decided_on=decision.decided_on,
            records=tuple(records),
        )
        self.archive.save_manifest(manifest)
        return manifest

    def _fetch(
        self, target: Target, *, max_bytes: int | None = None
    ) -> tuple[FetchRecord, Path | None]:
        slot = (target.dataset_id, target.key)
        latest = self.archive.latest(*slot)
        now = self._now()
        before = self.client.requests_made

        def record(outcome: Outcome, **extra: object) -> FetchRecord:
            return FetchRecord.model_validate(
                {
                    "dataset_id": target.dataset_id,
                    "key": target.key,
                    "url": target.url,
                    "outcome": outcome,
                    "requests": self.client.requests_made - before,
                    "checked_at": now,
                    **extra,
                }
            )

        def archived(
            outcome: Outcome, kept: RawObject, **extra: object
        ) -> tuple[FetchRecord, Path | None]:
            found = record(outcome, sha256=kept.sha256, size_bytes=kept.size_bytes, **extra)
            return found, self.archive.root / kept.path

        checked = self._checked.get(slot)
        if latest is not None and checked is not None and now - checked < self._max_age:
            return archived(Outcome.FRESH_IN_ARCHIVE, latest)
        validators = Validators(latest.etag, latest.last_modified) if latest else None
        limit = self.archive.remaining_bytes() if max_bytes is None else max_bytes
        try:
            fetched = self.client.get(target.url, max_bytes=limit, validators=validators)
        except (RetriesExhaustedError, HttpStatusError) as exc:
            return record(Outcome.FAILED, error=str(exc)), None
        if fetched.status == 304 and latest is not None:
            self._checked[slot] = now
            return archived(Outcome.NOT_MODIFIED, latest)
        if fetched.path is None:
            return record(Outcome.FAILED, error=f"HTTP {fetched.status} without a body"), None
        last_modified = fetched.headers.get("last-modified")
        if latest is not None and _older(last_modified, latest.last_modified):
            fetched.path.unlink()
            return archived(
                Outcome.STALE_RESPONSE,
                latest,
                error=f"Last-Modified {last_modified} is older than the archived copy",
            )
        try:
            summary = target.check(fetched.path)
        except InvalidPayloadError as exc:
            fetched.path.unlink()
            return record(Outcome.FAILED, error=str(exc)), None

        def describe(sha: str, size: int, path: str) -> RawObject:
            return RawObject(
                source_id=self.source.source_id,
                dataset_id=target.dataset_id,
                key=target.key,
                cik=target.cik,
                url=target.url,
                path=path,
                sha256=sha,
                size_bytes=size,
                file_format=target.file_format,
                content_encoding=fetched.headers.get("content-encoding", "identity"),
                http_status=fetched.status,
                content_length=fetched.content_length,
                last_modified=last_modified,
                etag=fetched.headers.get("etag"),
                downloaded_at=now,
                run_id=self._run_id,
                filing_count=summary.filing_count,
                latest_filing_id=summary.latest_filing_id,
                latest_filed=summary.latest_filed,
                licence=self.source.licence.name,
                terms_checked_on=self.source.verified_on,
                catalog_version=self._catalog_version,
            )

        stored, created = self.archive.store(
            fetched.path,
            dataset_id=target.dataset_id,
            key=target.key,
            file_format=target.file_format,
            describe=describe,
        )
        self._checked[slot] = now
        return (
            record(
                Outcome.NEW if created else Outcome.UNCHANGED,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                content_length=fetched.content_length,
                last_modified=last_modified,
            ),
            self.archive.root / stored.path,
        )
