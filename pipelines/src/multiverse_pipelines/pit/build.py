"""Build the warehouse from the local raw archive of Stage 10 (no network).

For each company: the latest archived Company Facts file, the latest submissions file
and its paged files. ``known_by`` simulates an archive downloaded at that moment: only
facts and filings public by then are read. A snapshot from such a build must equal the
snapshot of the full build at the same cutoff; ``leakage-check`` compares the two.
"""

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from itertools import repeat
from pathlib import Path
from typing import Any

from multiverse_contracts.pit import ChronologyAlert, EntityAttribute, SnapshotInput
from multiverse_pipelines.pit.alerts import filing_alerts, sum_alerts
from multiverse_pipelines.pit.filings import (
    Filing,
    FilingIndex,
    attributes_from_submissions,
    filings_from_tables,
)
from multiverse_pipelines.pit.vintages import CompanyHistory, build_history
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.cik import cik10
from multiverse_pipelines.sec.ingest import COMPANYFACTS, SUBMISSIONS
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.sec.validate import load_json
from multiverse_pipelines.xbrl.facts import Fact, facts_from_companyfacts


@dataclass(frozen=True)
class CompanyInputs:
    cik: str
    facts: list[Fact]
    submissions: dict[str, Any]
    pages: list[dict[str, Any]]
    observed_at: datetime
    files: list[RawObject]


def _latest_per_key(archive: RawArchive, dataset: str, prefix: str) -> list[RawObject]:
    latest: dict[str, RawObject] = {}
    for row in archive.objects():
        if row.dataset_id != dataset or not (row.key == prefix or row.key.startswith(prefix + "/")):
            continue
        known = latest.get(row.key)
        if known is None or row.downloaded_at > known.downloaded_at:
            latest[row.key] = row
    return [latest[key] for key in sorted(latest)]


def load_inputs(archive: RawArchive, cik: str) -> CompanyInputs:
    cik = cik10(cik)
    facts_file = archive.latest(COMPANYFACTS, f"CIK{cik}")
    submissions = _latest_per_key(archive, SUBMISSIONS, f"CIK{cik}")
    main = next((row for row in submissions if row.key == f"CIK{cik}"), None)
    if facts_file is None or main is None:
        raise ValueError(
            f"CIK {cik}: company facts or submissions not archived; run the SEC sample"
        )
    pages = [load_json(archive.root / row.path) for row in submissions if row is not main]
    return CompanyInputs(
        cik=cik,
        facts=facts_from_companyfacts(load_json(archive.root / facts_file.path)),
        submissions=load_json(archive.root / main.path),
        pages=pages,
        observed_at=main.downloaded_at,
        files=[facts_file, *submissions],
    )


@dataclass(frozen=True)
class Prepared:
    history: CompanyHistory
    filings: list[Filing]
    attributes: list[EntityAttribute]
    alerts: list[ChronologyAlert]
    files: list[SnapshotInput]


def prepare(inputs: CompanyInputs, known_by: datetime | None = None) -> Prepared:
    """Everything one company adds to the warehouse (runs in a worker process)."""
    tables = [inputs.submissions["filings"]["recent"], *inputs.pages]
    filings = filings_from_tables(tables)
    facts = inputs.facts
    if known_by is not None:
        everything = FilingIndex(filings)
        filings = [f for f in filings if f.known_at <= known_by]
        facts = [f for f in facts if everything.timing(f.accession, f.filed).known_at <= known_by]
    index = FilingIndex(filings)
    history = build_history(inputs.cik, facts, index)
    first = index.first_filing()
    attributes = attributes_from_submissions(
        inputs.cik, inputs.submissions, inputs.observed_at, first.filing_date if first else None
    )
    alerts = (
        history.alerts
        + filing_alerts(inputs.cik, index, frozenset(f.accession for f in facts))
        + sum_alerts(inputs.cik, history.values)
    )
    files = [
        SnapshotInput(path=f.path, sha256=f.sha256, url=f.url, downloaded_at=f.downloaded_at)
        for f in inputs.files
    ]
    return Prepared(history, filings, attributes, alerts, files)


def build_warehouse(
    archive: RawArchive,
    ciks: Sequence[str],
    path: Path | None,
    *,
    built_at: datetime,
    known_by: datetime | None = None,
    workers: int = 1,
) -> Warehouse:
    """Companies are independent: with ``workers`` > 1 they are normalized in parallel."""
    loaded = [load_inputs(archive, cik) for cik in ciks]
    if workers > 1 and len(loaded) > 1:
        with ProcessPoolExecutor(min(workers, len(loaded))) as pool:
            prepared = list(pool.map(prepare, loaded, repeat(known_by)))
    else:
        prepared = [prepare(inputs, known_by) for inputs in loaded]
    warehouse = Warehouse.create(path, built_at=built_at)
    for item in prepared:
        warehouse.add_company(item.history, item.filings, item.attributes, item.alerts, item.files)
    return warehouse
