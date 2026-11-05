"""The sample of filings to read: written rules and a seed, so it can be repeated.

Strata follow what the filing index can point to:

- ``item_2_01``: completed acquisitions and disposals of assets (8-K Item 2.01). The item
  covers both directions, so the reader decides between acquisition and divestiture;
- ``item_2_05``: exit and disposal plans, the usual home of layoffs (Item 2.05);
- ``item_2_03``: new direct financial obligations (Item 2.03), candidates for refinancing;
- ``rnd_jump``, ``capex_jump``: a yearly change of intensity in the Stage 15 dataset, with
  the first 10-K filed after it: these decisions leave no 8-K item.

A third of every stratum comes from companies that later left EDGAR reporting, so a sample
of survivors cannot tell the whole story. Only filings from 2012 on are drawn: the panel
of Stage 12 has too little before.
"""

import csv
import hashlib
import json
import math
import random
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from multiverse_contracts.events import CandidateSample, EventCandidate, EventType
from multiverse_contracts.universe import UniverseManifest
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.pit.clock import knowledge_time

ITEMS = {
    "2.01": ("item_2_01", EventType.ACQUISITION, 24),
    "2.05": ("item_2_05", EventType.LAYOFF, 12),
    "2.03": ("item_2_03", EventType.REFINANCING, 12),
}
JUMPS = {
    "rnd_intensity_ttm": ("rnd_jump", EventType.RND_CHANGE, 6),
    "capex_intensity_ttm": ("capex_jump", EventType.CAPEX_CHANGE, 6),
}
FIRST_YEAR = 2012
DEREGISTERED_SHARE = 1 / 3
MIN_REVENUE = 10_000_000.0
MIN_CHANGE = 0.03
MIN_RATIO = 1.5


@dataclass(frozen=True)
class Filing:
    cik: str
    form: str
    filed_on: date
    accepted: str
    accession: str
    document: str
    items: tuple[str, ...]


def document_url(cik: str, accession: str, document: str) -> str:
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}/{document}"
    )


def rows_of(table: dict[str, list[str]], cik: str) -> list[Filing]:
    found: list[Filing] = []
    for form, items, filed, accepted, accession, document in zip(
        table["form"],
        table["items"],
        table["filingDate"],
        table["acceptanceDateTime"],
        table["accessionNumber"],
        table["primaryDocument"],
        strict=True,
    ):
        if form not in ("8-K", "10-K") or not document:
            continue
        parts = tuple(p.strip() for p in str(items).split(",") if p.strip())
        found.append(
            Filing(cik, form, date.fromisoformat(filed), accepted, accession, document, parts)
        )
    return found


def filings_of(archive: zipfile.ZipFile, ciks: list[str]) -> dict[str, list[Filing]]:
    """The 8-K and 10-K filings of the companies, from the archived submissions ZIP."""
    names: dict[str, list[str]] = defaultdict(list)
    for name in archive.namelist():
        names[name[3:13]].append(name)
    found: dict[str, list[Filing]] = {}
    for cik in ciks:
        rows: list[Filing] = []
        for name in sorted(names[cik]):
            document = json.loads(archive.read(name))
            table = document["filings"]["recent"] if "filings" in document else document
            rows += rows_of(table, cik)
        found[cik] = sorted(rows, key=lambda f: (f.filed_on, f.accession))
    return found


def jumps(dataset_csv: Path, column: str) -> list[tuple[str, date]]:
    """Company and origin where a yearly intensity moved by at least the set amounts."""
    by_firm: dict[str, dict[date, tuple[float, float]]] = defaultdict(dict)
    with dataset_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row[column] and row["rev_ttm"]:
                by_firm[row["cik"]][date.fromisoformat(row["origin"])] = (
                    float(row[column]),
                    float(row["rev_ttm"]),
                )
    found: list[tuple[str, date]] = []
    for cik, series in sorted(by_firm.items()):
        for origin, (value, revenue) in sorted(series.items()):
            if origin.month == 2 and origin.day == 29:
                continue
            before = series.get(origin.replace(year=origin.year - 1))
            if before is None or revenue < MIN_REVENUE or before[1] < MIN_REVENUE:
                continue
            change = abs(value - before[0])
            low, high = sorted((abs(value), abs(before[0])))
            if change >= MIN_CHANGE and low > 0 and high / low >= MIN_RATIO:
                found.append((cik, origin))
    return found


def candidate_of(
    filing: Filing, name: str, division: str, deregistered: bool, kind: EventType, stratum: str
) -> EventCandidate:
    accepted = datetime.fromisoformat(filing.accepted.replace("Z", "+00:00"))
    moment, _ = knowledge_time(filing.filed_on, accepted)
    return EventCandidate(
        candidate_id=f"{stratum}-{filing.accession}",
        cik=filing.cik,
        company=name,
        division=division,
        deregistered=deregistered,
        event_type=kind,
        stratum=stratum,
        accession=filing.accession,
        form=filing.form,
        items=filing.items,
        filed_at=moment,
        url=document_url(filing.cik, filing.accession, filing.document),
    )


def draw(pool: list[EventCandidate], size: int, rng: random.Random) -> list[EventCandidate]:
    """At most one filing per company, a third from companies that left, by seed."""
    ordered = sorted(pool, key=lambda c: c.candidate_id)
    rng.shuffle(ordered)
    gone = [c for c in ordered if c.deregistered]
    alive = [c for c in ordered if not c.deregistered]
    chosen: list[EventCandidate] = []
    seen: set[str] = set()
    for group, quota in ((gone, math.ceil(size * DEREGISTERED_SHARE)), (alive, size)):
        count = 0
        for candidate in group:
            if len(chosen) == size or count == quota:
                break
            if candidate.cik not in seen:
                seen.add(candidate.cik)
                chosen.append(candidate)
                count += 1
    return chosen


def sample(
    universe: UniverseManifest, submissions_zip: Path, dataset_csv: Path, seed: int, day: date
) -> CandidateSample:
    ciks = [c.cik for c in universe.companies]
    meta = {c.cik: c for c in universe.companies}
    with zipfile.ZipFile(submissions_zip) as archive:
        filings = filings_of(archive, ciks)
    pools: dict[str, list[EventCandidate]] = defaultdict(list)
    sizes: dict[str, int] = {}
    for item, (stratum, kind, size) in ITEMS.items():
        sizes[stratum] = size
        for cik in ciks:
            firm = meta[cik]
            pools[stratum] += [
                candidate_of(f, firm.name, firm.division, firm.deregistered, kind, stratum)
                for f in filings[cik]
                if f.form == "8-K" and item in f.items and f.filed_on.year >= FIRST_YEAR
            ]
    for column, (stratum, kind, size) in JUMPS.items():
        sizes[stratum] = size
        for cik, origin in jumps(dataset_csv, column):
            listed = meta.get(cik)
            if listed is None:
                continue
            after = [
                f
                for f in filings[cik]
                if f.form == "10-K" and origin <= f.filed_on <= origin + timedelta(days=400)
            ]
            if after:
                pools[stratum].append(
                    candidate_of(
                        after[0], listed.name, listed.division, listed.deregistered, kind, stratum
                    )
                )
    rng = random.Random(seed)
    chosen: list[EventCandidate] = []
    population: dict[str, int] = {}
    drawn: dict[str, int] = {}
    for stratum in sorted(pools):
        population[stratum] = len(pools[stratum])
        picked = draw(pools[stratum], sizes[stratum], rng)
        drawn[stratum] = len(picked)
        chosen += picked
    payload = json.dumps(
        [c.model_dump(mode="json") for c in chosen], sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return CandidateSample(
        sample_id=f"evs-{day:%Y%m%d}-{digest[:12]}",
        sha256=digest,
        universe_id=universe.universe_id,
        seed=seed,
        population=population,
        drawn=drawn,
        candidates=tuple(chosen),
        contracts_version=CONTRACTS_VERSION,
        created_at=datetime.now(UTC),
    )
