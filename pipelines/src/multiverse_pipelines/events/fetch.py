"""The documents of the sample, within decision D-13 (150 documents, 200 MB).

Behind the three locks of every download; each file goes into the raw archive by its hash
and is never changed. A document already stored is not fetched again.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from multiverse_contracts.events import CandidateSample, EventCandidate
from multiverse_contracts.sources import DataSource
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.client import Fetched, SecClient
from multiverse_pipelines.sec.errors import IngestionError
from multiverse_pipelines.sec.models import FetchRecord, Outcome, RawObject, RunManifest, RunStatus

DOCUMENTS = "sec-filing-documents"
MAX_DOCUMENTS = 150
MAX_BYTES = 200 * 1024 * 1024
MAX_DOCUMENT_BYTES = 40 * 1024 * 1024


def key_of(candidate: EventCandidate) -> str:
    return f"{candidate.cik}/{candidate.accession}"


def stored_path(archive: RawArchive, candidate: EventCandidate) -> Path | None:
    row = archive.latest(DOCUMENTS, key_of(candidate))
    return None if row is None else archive.root / row.path


def raw_object(
    source: DataSource,
    candidate: EventCandidate,
    fetched: Fetched,
    moment: datetime,
    run_id: str,
    catalog_version: str,
    sha: str,
    size: int,
    path: str,
) -> RawObject:
    return RawObject(
        source_id=source.source_id,
        dataset_id=DOCUMENTS,
        key=key_of(candidate),
        cik=candidate.cik,
        url=candidate.url,
        path=path,
        sha256=sha,
        size_bytes=size,
        file_format="html",
        content_encoding=fetched.headers.get("content-encoding", "identity"),
        http_status=fetched.status,
        content_length=fetched.content_length,
        last_modified=fetched.headers.get("last-modified"),
        etag=fetched.headers.get("etag"),
        downloaded_at=moment,
        run_id=run_id,
        latest_filing_id=candidate.accession,
        latest_filed=candidate.filed_at.date(),
        licence=source.licence.name,
        terms_checked_on=source.verified_on,
        catalog_version=catalog_version,
    )


def fetch_documents(
    client: SecClient,
    archive: RawArchive,
    source: DataSource,
    sample: CandidateSample,
    catalog_version: str,
    run_id: str,
    progress: Callable[[str], None] = print,
) -> RunManifest:
    started = datetime.now(UTC)
    records: list[FetchRecord] = []
    total = sum(row.size_bytes for row in archive.objects() if row.dataset_id == DOCUMENTS)
    if len(sample.candidates) > MAX_DOCUMENTS:
        raise ValueError(f"{len(sample.candidates)} documents exceed decision D-13")
    status, message = RunStatus.COMPLETED, None
    for number, candidate in enumerate(sample.candidates, start=1):
        key = key_of(candidate)
        now = datetime.now(UTC)
        common = {"dataset_id": DOCUMENTS, "key": key, "url": candidate.url, "checked_at": now}
        if archive.latest(DOCUMENTS, key) is not None:
            records.append(
                FetchRecord.model_validate(
                    common | {"outcome": Outcome.FRESH_IN_ARCHIVE, "requests": 0}
                )
            )
            continue
        if total >= MAX_BYTES:
            status, message = RunStatus.ABORTED, "the 200 MB of decision D-13 are used up"
            break
        before = client.requests_made
        try:
            fetched = client.get(candidate.url, max_bytes=MAX_DOCUMENT_BYTES)
        except IngestionError as error:
            records.append(
                FetchRecord.model_validate(
                    common
                    | {
                        "outcome": Outcome.FAILED,
                        "requests": client.requests_made - before,
                        "error": str(error),
                    }
                )
            )
            continue

        if fetched.path is None:
            records.append(
                FetchRecord.model_validate(
                    common | {"outcome": Outcome.FAILED, "requests": 1, "error": "empty answer"}
                )
            )
            continue
        describe = partial(raw_object, source, candidate, fetched, now, run_id, catalog_version)
        stored, created = archive.store(
            fetched.path, dataset_id=DOCUMENTS, key=key, file_format="html", describe=describe
        )
        total += stored.size_bytes
        records.append(
            FetchRecord.model_validate(
                common
                | {
                    "outcome": Outcome.NEW if created else Outcome.UNCHANGED,
                    "requests": client.requests_made - before,
                    "sha256": stored.sha256,
                    "size_bytes": stored.size_bytes,
                }
            )
        )
        progress(f"{number}/{len(sample.candidates)} {key} {stored.size_bytes} bytes")
    download = source.download
    return RunManifest(
        run_id=run_id,
        mode="documents",
        started_at=started,
        finished_at=datetime.now(UTC),
        status=status,
        message=message,
        rate_per_second=source.rate_limit.chosen_requests_per_second,
        catalog_version=catalog_version,
        decision_status=str(download.status),
        decision_scope=None if download.scope is None else str(download.scope),
        decided_on=download.decided_on,
        records=tuple(records),
    )
