"""Build the warehouse from the local raw archive of Stage 10 (no network).

For each company: the latest archived Company Facts file, the latest submissions file
and its paged files. ``known_by`` simulates an archive downloaded at that moment: only
facts and filings public by then are read. A snapshot from such a build must equal the
snapshot of the full build at the same cutoff; ``leakage-check`` compares the two.

A file copied out of a bulk ZIP holds what the SEC had published when it built the ZIP,
which can be hours before the download: such a file counts as observed at the ZIP's
``Last-Modified`` time, the earlier of the two.

Companies are independent. With several workers each one reads and normalizes its own
companies and sends back encoded rows; the parent inserts them in CIK order, one
transaction per company, so memory holds a few companies at a time, never the universe.
"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
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
from multiverse_pipelines.pit.warehouse import (
    CompanyRows,
    Warehouse,
    company_rows,
    make_dictionary,
)
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


@dataclass(frozen=True)
class CompanyFiles:
    """The archived files one company is built from: its latest of each key."""

    root: Path
    cik: str
    facts: RawObject
    submissions: RawObject
    pages: tuple[RawObject, ...]


def observed_at(row: RawObject) -> datetime:
    """When a file's content was current: its download, or the ZIP's build if earlier."""
    if row.last_modified and "#" in row.url:
        return min(row.downloaded_at, parsedate_to_datetime(row.last_modified))
    return row.downloaded_at


def archived_files(archive: RawArchive) -> Callable[[str], CompanyFiles]:
    """Read the archive index once; return a lookup of each company's latest files."""
    latest: dict[tuple[str, str], RawObject] = {}
    for row in archive.objects():
        slot = (row.dataset_id, row.key)
        known = latest.get(slot)
        if known is None or row.downloaded_at > known.downloaded_at:
            latest[slot] = row
    pages: dict[str, list[RawObject]] = defaultdict(list)
    for (dataset, key), row in latest.items():
        if dataset == SUBMISSIONS and "/" in key and key.startswith("CIK"):
            pages[key.split("/", 1)[0]].append(row)

    def lookup(cik: str) -> CompanyFiles:
        cik = cik10(cik)
        facts = latest.get((COMPANYFACTS, f"CIK{cik}"))
        main = latest.get((SUBMISSIONS, f"CIK{cik}"))
        if facts is None or main is None:
            raise ValueError(
                f"CIK {cik}: company facts or submissions not archived; run the SEC sample "
                "or copy the universe out of the bulk files (`sec universe`)"
            )
        found = sorted(pages.get(f"CIK{cik}", []), key=lambda row: row.key)
        return CompanyFiles(archive.root, cik, facts, main, tuple(found))

    return lookup


def read_inputs(files: CompanyFiles) -> CompanyInputs:
    return CompanyInputs(
        cik=files.cik,
        facts=facts_from_companyfacts(load_json(files.root / files.facts.path)),
        submissions=load_json(files.root / files.submissions.path),
        pages=[load_json(files.root / row.path) for row in files.pages],
        observed_at=observed_at(files.submissions),
        files=[files.facts, files.submissions, *files.pages],
    )


def load_inputs(archive: RawArchive, cik: str) -> CompanyInputs:
    return read_inputs(archived_files(archive)(cik))


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
        SnapshotInput(path=f.path, sha256=f.sha256, url=f.url, downloaded_at=observed_at(f))
        for f in inputs.files
    ]
    return Prepared(history, filings, attributes, alerts, files)


def _rows(item: Prepared, dictionary: bytes) -> CompanyRows:
    return company_rows(
        item.history, item.filings, item.attributes, item.alerts, item.files, dictionary
    )


def build_company(files: CompanyFiles, known_by: datetime | None, dictionary: bytes) -> CompanyRows:
    """One company from its files to encoded rows (runs in a worker process)."""
    return _rows(prepare(read_inputs(files), known_by), dictionary)


def build_warehouse(
    archive: RawArchive,
    ciks: Sequence[str],
    path: Path | None,
    *,
    built_at: datetime,
    known_by: datetime | None = None,
    workers: int = 1,
    progress: Callable[[int, int, str], None] | None = None,
) -> Warehouse:
    """The first company primes the payload dictionary; the others follow in parallel."""
    lookup = archived_files(archive)
    files = [lookup(cik) for cik in sorted({cik10(c) for c in ciks})]
    if not files:
        return Warehouse.create(path, built_at=built_at)
    first = prepare(read_inputs(files[0]), known_by)
    dictionary = make_dictionary(first.history.values)
    warehouse = Warehouse.create(path, built_at=built_at, dictionary=dictionary)
    warehouse.insert(_rows(first, dictionary))
    if progress is not None:
        progress(1, len(files), files[0].cik)
    rest = files[1:]
    if workers > 1 and len(rest) > 1:
        with ProcessPoolExecutor(min(workers, len(rest))) as pool:
            done = pool.map(build_company, rest, repeat(known_by), repeat(dictionary))
            for number, rows in enumerate(done, start=2):
                warehouse.insert(rows)
                if progress is not None:
                    progress(number, len(files), rows.cik)
    else:
        for number, item in enumerate(rest, start=2):
            warehouse.insert(build_company(item, known_by, dictionary))
            if progress is not None:
                progress(number, len(files), item.cik)
    return warehouse
