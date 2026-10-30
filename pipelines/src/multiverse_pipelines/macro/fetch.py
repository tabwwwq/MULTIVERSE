"""Downloads of macro series into the raw archive, behind the same locks as SEC (ADR-0017).

1. ``MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true`` for this command only.
2. The owner's decision in the source catalog: approved (D-11 for FRED, D-12 for ECB
   and the World Bank). Both are pending, so every fetch is refused today.
3. For FRED, ``MULTIVERSE_FRED_API_KEY``. The key is sent as the API requires and never
   stored: archived URLs and messages show ``api_key=REDACTED``.

FRED requests ask for the full real-time range, so one file holds every vintage. Before
storing a FRED series, its notes are checked for "copyright": third-party series need
the copyright holder's permission under the FRED terms.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import httpx

from multiverse_config import Settings
from multiverse_contracts.macro import VintageSupport
from multiverse_contracts.sources import DataSource, DecisionStatus
from multiverse_pipelines.macro.registry import SERIES
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.client import Fetched, SecClient
from multiverse_pipelines.sec.errors import IngestionError, PermissionRefusedError
from multiverse_pipelines.sec.models import RawObject

USER_AGENT = "MULTIVERSE research pipeline (macro vintages)"
FRED_BASE = "https://api.stlouisfed.org/fred"
ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
WB_BASE = "https://api.worldbank.org/v2"
MAX_BYTES = 20 * 1024 * 1024
DECISIONS = {"fred-alfred": "D-11", "ecb-data-portal": "D-12", "world-bank": "D-12"}


class MissingKeyError(PermissionRefusedError):
    """FRED needs the owner's API key in MULTIVERSE_FRED_API_KEY."""


def unavailable_reason(settings: Settings, source: DataSource) -> str:
    """Why a source has nothing in the store, for the cells of the join."""
    decision = DECISIONS.get(source.source_id, "?")
    if source.source_id == "fred-alfred" and settings.fred_api_key is None:
        return f"MULTIVERSE_FRED_API_KEY is not set: the owner registers the FRED key ({decision})"
    if source.download.status is not DecisionStatus.APPROVED:
        return f"{source.name}: owner decision {decision} pending, nothing downloaded"
    return f"{source.name}: approved, but nothing downloaded yet (run fetch)"


def require_macro_permission(settings: Settings, source: DataSource) -> str | None:
    """Return the FRED key when every lock is open; otherwise say which one is closed."""
    if not settings.allow_network_downloads:
        raise PermissionRefusedError(
            "Network downloads are off. Set MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true for this "
            "command only; .env keeps it false."
        )
    if source.download.status is not DecisionStatus.APPROVED:
        raise PermissionRefusedError(
            f"{source.source_id}: the owner has not approved downloads "
            f"({source.download.status}, decision {DECISIONS.get(source.source_id, '?')})."
        )
    if source.source_id != "fred-alfred":
        return None
    if settings.fred_api_key is None:
        raise MissingKeyError(
            "MULTIVERSE_FRED_API_KEY is not set. The owner registers a key at "
            "https://fredaccount.stlouisfed.org and puts it into .env; it is never committed."
        )
    return settings.fred_api_key.get_secret_value()


def redact_text(text: str) -> str:
    """Any ``api_key=...`` in a message or URL replaced, so an error never shows the key."""
    return re.sub(r"api_key=[^&\s'\"]+", "api_key=REDACTED", text)


def redact(url: str) -> str:
    head, _, query = url.partition("?")
    parts = [p if not p.startswith("api_key=") else "api_key=REDACTED" for p in query.split("&")]
    return head + ("?" + "&".join(parts) if query else "")


@dataclass
class FetchReport:
    stored: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    requests: int = 0


def _client(
    source: DataSource, archive: RawArchive, transport: httpx.BaseTransport | None
) -> SecClient:
    archive.tmp_dir.mkdir(parents=True, exist_ok=True)
    return SecClient(
        user_agent=USER_AGENT,
        allowed_hosts=source.official_hosts,
        rate_per_second=Decimal(source.rate_limit.chosen_requests_per_second),
        tmp_dir=archive.tmp_dir,
        transport=transport,
    )


def _store(
    archive: RawArchive,
    source: DataSource,
    fetched: Fetched,
    *,
    dataset_id: str,
    key: str,
    file_format: str,
    url: str,
    run_id: str,
    catalog_version: str,
) -> tuple[RawObject, bool]:
    if fetched.path is None:
        raise IngestionError(f"{redact(url)}: no body to store")

    def describe(sha: str, size: int, path: str) -> RawObject:
        return RawObject(
            source_id=source.source_id,
            dataset_id=dataset_id,
            key=key,
            url=redact(url),
            path=path,
            sha256=sha,
            size_bytes=size,
            file_format=file_format,  # type: ignore[arg-type]
            content_encoding=fetched.headers.get("content-encoding", "identity"),
            http_status=fetched.status,
            content_length=fetched.content_length,
            last_modified=fetched.headers.get("last-modified"),
            etag=fetched.headers.get("etag"),
            downloaded_at=datetime.now(UTC),
            run_id=run_id,
            licence=source.licence.name,
            terms_checked_on=source.verified_on,
            catalog_version=catalog_version,
        )

    return archive.store(
        fetched.path, dataset_id=dataset_id, key=key, file_format=file_format, describe=describe
    )


def fetch_source(
    settings: Settings,
    source: DataSource,
    archive: RawArchive,
    *,
    run_id: str,
    catalog_version: str,
    transport: httpx.BaseTransport | None = None,
    series_ids: Sequence[str] | None = None,
) -> FetchReport:
    """Download the registered series of one source; refused unless every lock is open."""
    try:
        return _fetch(settings, source, archive, run_id, catalog_version, transport, series_ids)
    except IngestionError as exc:
        raise type(exc)(redact_text(str(exc))) from None


def _fetch(
    settings: Settings,
    source: DataSource,
    archive: RawArchive,
    run_id: str,
    catalog_version: str,
    transport: httpx.BaseTransport | None,
    series_ids: Sequence[str] | None,
) -> FetchReport:
    key = require_macro_permission(settings, source)
    wanted = [s for s in SERIES if s.source_id == source.source_id]
    if series_ids:
        wanted = [s for s in wanted if s.series_id in series_ids]
    report = FetchReport()
    seen_wb: set[str] = set()
    with _client(source, archive, transport) as client:
        for series in wanted:
            code = series.series_id.split(":", 1)[1]
            if source.source_id == "fred-alfred":
                meta_url = f"{FRED_BASE}/series?" + urlencode(
                    {"series_id": code, "api_key": key, "file_type": "json"}
                )
                meta = client.get(meta_url, max_bytes=MAX_BYTES)
                notes = json.loads(Path(str(meta.path)).read_text(encoding="utf-8"))["seriess"][
                    0
                ].get("notes", "")
                Path(str(meta.path)).unlink(missing_ok=True)
                if "copyright" in notes.lower():
                    report.skipped.append(f"{series.series_id}: notes mention copyright")
                    continue
                query = {"series_id": code, "api_key": key, "file_type": "json"}
                if series.vintage_support is VintageSupport.FULL:
                    query |= {"realtime_start": "1776-07-04", "realtime_end": "9999-12-31"}
                url = f"{FRED_BASE}/series/observations?" + urlencode(query)
                dataset, file_key, file_format = "fred-series-observations", code, "json"
            elif source.source_id == "ecb-data-portal":
                flow, _, rest = code.partition(".")
                url = f"{ECB_BASE}/{flow}/{rest}?format=csvdata"
                dataset, file_key, file_format = "ecb-series", code, "csv"
            else:
                indicator = code.split(".", 1)[1]
                if indicator in seen_wb:
                    continue
                seen_wb.add(indicator)
                url = f"{WB_BASE}/country/USA;EMU/indicator/{indicator}?format=json&per_page=20000"
                dataset, file_key, file_format = "wb-wdi", indicator, "json"
            fetched = client.get(url, max_bytes=min(MAX_BYTES, archive.remaining_bytes()))
            row, new = _store(
                archive,
                source,
                fetched,
                dataset_id=dataset,
                key=file_key,
                file_format=file_format,
                url=url,
                run_id=run_id,
                catalog_version=catalog_version,
            )
            (report.stored if new else report.unchanged).append(row.path)
        report.requests = client.requests_made
    return report
