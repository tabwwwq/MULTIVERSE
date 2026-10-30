"""The study universe: a seeded, stratified sample of companies from the bulk files.

Decision D-10 (2026-10-30) approved the bulk Company Facts and Submissions files for a
universe of 1000 companies. Both ZIP files are read where they are archived; nothing is
downloaded. A company is eligible when, in this order,

1. it has a Company Facts file and a submissions file;
2. its submissions list at least 12 XBRL 10-K or 10-Q filings, at least one a 10-K:
   three years of reports, the shortest history Gate B counts;
3. its SIC code is set and outside the sectors the catalog excludes (banks, insurers,
   REITs, asset managers, blank-check companies; their statements do not have the
   revenue, margin and capex structure the metrics assume);
4. its Company Facts hold one of the four US-GAAP revenue concepts of Stage 11, so the
   forecasting target can exist at all.

Deregistered, bankrupt and acquired companies stay eligible: a sample of the survivors
only would bias every later result. The sample is stratified by SIC division, each
division's share proportional to its eligible companies (largest remainder), drawn in a
seeded random order; the ten catalog candidates are always in it and count against the
share of their division. The chosen companies' files are copied out of the ZIP files
into the raw archive byte for byte, addressed as ``<zip url>#<member>``.
"""

import json
import random
import re
import uuid
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

from multiverse_contracts.sources import SectorPriority
from multiverse_contracts.universe import (
    BulkFile,
    RuleCount,
    UniverseCompany,
    UniverseManifest,
    UniverseStratum,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.pit.filings import DEREGISTRATION_PREFIXES
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.ingest import COMPANYFACTS, SUBMISSIONS
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.sec.validate import (
    Summary,
    check_companyfacts,
    check_submissions,
    check_submissions_page,
)
from multiverse_pipelines.xbrl.concepts import METRICS

MIN_REPORTS = 12
REPORT_FORMS = ("10-K", "10-Q")
FACTS_MEMBER = re.compile(r"^CIK(\d{10})\.json$")
PAGE_MEMBER = re.compile(r"^CIK(\d{10})-submissions-(\d{3})\.json$")
REVENUE = next(spec for spec in METRICS if spec.metric == "revenue")
# A concept is a key whose value is an object: '"Revenues":{"label":...'.
REVENUE_KEY = re.compile(
    rb'"(?:'
    + b"|".join(re.escape(c.concept.removeprefix("us-gaap:").encode()) for c in REVENUE.candidates)
    + rb')"\s*:\s*\{'
)
DIVISIONS = (
    ("A", "Agriculture, forestry and fishing", 100, 999),
    ("B", "Mining", 1000, 1499),
    ("C", "Construction", 1500, 1799),
    ("D", "Manufacturing", 2000, 3999),
    ("E", "Transportation, communications, utilities", 4000, 4999),
    ("F", "Wholesale trade", 5000, 5199),
    ("G", "Retail trade", 5200, 5999),
    ("H", "Finance, insurance and real estate", 6000, 6799),
    ("I", "Services", 7000, 8999),
    ("J", "Public administration", 9100, 9729),
)
NONCLASSIFIABLE = ("K", "Nonclassifiable")
RULES = (
    "has a Company Facts file and a submissions file",
    f"at least {MIN_REPORTS} XBRL 10-K or 10-Q filings, at least one of them a 10-K",
    "a SIC code outside the sectors the catalog excludes "
    "(banks, insurers, REITs, asset managers, blank-check companies)",
    "a US-GAAP revenue concept among its Company Facts: "
    + ", ".join(c.concept.removeprefix("us-gaap:") for c in REVENUE.candidates),
)


@dataclass(frozen=True)
class Scanned:
    """What the bulk files say about one company, enough to decide its eligibility."""

    cik: str
    name: str
    sic: str | None
    xbrl_10k: int
    xbrl_10q: int
    first_xbrl_filed: date | None
    last_filed: date | None
    deregistered: bool
    has_submissions: bool
    revenue: bool | None = None
    """``None``: not looked at, because an earlier rule already left the company out."""

    @property
    def reports_enough(self) -> bool:
        return self.xbrl_10k >= 1 and self.xbrl_10k + self.xbrl_10q >= MIN_REPORTS


def division(sic: str) -> tuple[str, str]:
    code = int(sic)
    for letter, title, low, high in DIVISIONS:
        if low <= code <= high:
            return letter, title
    return NONCLASSIFIABLE


def excluded_ranges(sectors: Iterable[SectorPriority]) -> list[tuple[int, int]]:
    """SIC ranges of the catalog's excluded sectors: "6020-6036" or a single "6770"."""
    found = []
    for sector in sectors:
        if sector.priority != "excluded":
            continue
        for codes in sector.sic_codes:
            low, _, high = codes.partition("-")
            found.append((int(low), int(high or low)))
    return found


def sic_allowed(sic: str | None, excluded: Sequence[tuple[int, int]]) -> bool:
    if not sic or not sic.isdigit() or int(sic) == 0:
        return False
    return not any(low <= int(sic) <= high for low, high in excluded)


def read_tables(submissions: zipfile.ZipFile, cik: str) -> tuple[dict[str, Any], list[Any]]:
    """The main submissions file of a company and the filing tables of its older pages."""
    main = json.loads(submissions.read(f"CIK{cik}.json"))
    pages = [json.loads(submissions.read(p["name"])) for p in main["filings"].get("files", [])]
    return main, [main["filings"]["recent"], *pages]


def scan_company(
    cik: str,
    facts: zipfile.ZipFile,
    submissions: zipfile.ZipFile,
    excluded: Sequence[tuple[int, int]],
) -> Scanned:
    try:
        main, tables = read_tables(submissions, cik)
    except KeyError:
        return Scanned(cik, "", None, 0, 0, None, None, False, has_submissions=False)
    counts: Counter[str] = Counter()
    first: date | None = None
    last: date | None = None
    last_report: date | None = None
    last_deregistration: date | None = None
    for table in tables:
        for form, filed, xbrl in zip(
            table["form"], table["filingDate"], table["isXBRL"], strict=True
        ):
            day = date.fromisoformat(filed)
            last = day if last is None else max(last, day)
            if form.startswith(DEREGISTRATION_PREFIXES):
                last_deregistration = max(last_deregistration or day, day)
            if form in REPORT_FORMS:
                last_report = max(last_report or day, day)
                if xbrl:
                    counts[form] += 1
                    first = day if first is None else min(first, day)
    sic = str(main.get("sic") or "") or None
    scanned = Scanned(
        cik=cik,
        name=str(main.get("name") or ""),
        sic=sic,
        xbrl_10k=counts["10-K"],
        xbrl_10q=counts["10-Q"],
        first_xbrl_filed=first,
        last_filed=last,
        # A Form 15 with no periodic report after it: the company stopped reporting.
        deregistered=last_deregistration is not None
        and (last_report is None or last_deregistration >= last_report),
        has_submissions=True,
    )
    if not scanned.reports_enough or not sic_allowed(sic, excluded):
        return scanned
    raw = facts.read(f"CIK{cik}.json")
    return replace(scanned, revenue=REVENUE_KEY.search(raw) is not None)


def scan(
    facts_zip: Path,
    submissions_zip: Path,
    excluded: Sequence[tuple[int, int]],
    progress: Callable[[int, int], None] | None = None,
) -> list[Scanned]:
    """Every company with a Company Facts file, in CIK order."""
    with zipfile.ZipFile(facts_zip) as facts, zipfile.ZipFile(submissions_zip) as submissions:
        ciks = sorted(m[1] for n in facts.namelist() if (m := FACTS_MEMBER.fullmatch(n)))
        found = []
        for number, cik in enumerate(ciks, start=1):
            found.append(scan_company(cik, facts, submissions, excluded))
            if progress is not None:
                progress(number, len(ciks))
    return found


def eligibility(
    scanned: Sequence[Scanned], excluded: Sequence[tuple[int, int]]
) -> tuple[list[RuleCount], list[Scanned]]:
    """The rules in order, with the companies left after each, and the eligible ones."""
    tests: list[Callable[[Scanned], bool]] = [
        lambda c: c.has_submissions,
        lambda c: c.reports_enough,
        lambda c: sic_allowed(c.sic, excluded),
        lambda c: bool(c.revenue),
    ]
    left = list(scanned)
    counts = []
    for rule, test in zip(RULES, tests, strict=True):
        left = [c for c in left if test(c)]
        counts.append(RuleCount(rule=rule, remaining=len(left)))
    return counts, left


def allocate(eligible: dict[str, int], size: int) -> dict[str, int]:
    """Shares proportional to the eligible counts, rounded by the largest remainder."""
    total = sum(eligible.values())
    if size > total:
        raise ValueError(f"a universe of {size} needs more than the {total} eligible companies")
    exact = {key: Fraction(size * count, total) for key, count in eligible.items()}
    quota = {key: int(share) for key, share in exact.items()}
    by_remainder = sorted(exact, key=lambda key: (-(exact[key] - quota[key]), key))
    for key in by_remainder[: size - sum(quota.values())]:
        quota[key] += 1
    return quota


def select(
    eligible: Sequence[Scanned], size: int, seed: int, required: Iterable[str]
) -> tuple[list[UniverseStratum], list[Scanned]]:
    """A seeded random sample per division; the required companies are always in it."""
    must = set(required)
    missing = must - {c.cik for c in eligible}
    if missing:
        raise ValueError(f"required companies are not eligible: {', '.join(sorted(missing))}")
    groups: dict[str, list[Scanned]] = defaultdict(list)
    for company in sorted(eligible, key=lambda c: c.cik):
        groups[division(company.sic or "0")[0]].append(company)
    quotas = allocate({key: len(group) for key, group in groups.items()}, size)
    strata, chosen = [], []
    for key in sorted(groups):
        group = groups[key]
        first = [c for c in group if c.cik in must]
        rest = [c for c in group if c.cik not in must]
        if len(first) > quotas[key]:
            raise ValueError(f"division {key}: more required companies than its share")
        random.Random(f"{seed}:{key}").shuffle(rest)
        taken = first + rest[: quotas[key] - len(first)]
        chosen += taken
        title = division(group[0].sic or "0")[1]
        strata.append(
            UniverseStratum(
                division=key,
                title=title,
                eligible=len(group),
                quota=quotas[key],
                selected=len(taken),
            )
        )
    return strata, sorted(chosen, key=lambda c: c.cik)


def bulk_file(row: RawObject) -> BulkFile:
    return BulkFile(
        url=row.url,
        path=row.path,
        sha256=row.sha256,
        last_modified=row.last_modified,
        downloaded_at=row.downloaded_at,
    )


def manifest(
    *,
    universe_id: str,
    seed: int,
    size: int,
    created_at: datetime,
    sources: Sequence[RawObject],
    scanned: int,
    rules: Sequence[RuleCount],
    strata: Sequence[UniverseStratum],
    chosen: Sequence[Scanned],
    required: Iterable[str],
) -> UniverseManifest:
    must = set(required)
    companies = []
    for c in chosen:
        if c.sic is None or c.first_xbrl_filed is None or c.last_filed is None:
            raise ValueError(f"CIK {c.cik} lacks the fields of an eligible company")
        companies.append(
            UniverseCompany(
                cik=c.cik,
                name=c.name,
                sic=c.sic,
                division=division(c.sic)[0],
                xbrl_10k=c.xbrl_10k,
                xbrl_10q=c.xbrl_10q,
                first_xbrl_filed=c.first_xbrl_filed,
                last_filed=c.last_filed,
                deregistered=c.deregistered,
                candidate=c.cik in must,
            )
        )
    return UniverseManifest(
        universe_id=universe_id,
        decision="D-10 (owner, 2026-10-30): the bulk Company Facts and Submissions files, "
        "for a universe of 1000 companies",
        seed=seed,
        size=size,
        created_at=created_at,
        sources=tuple(bulk_file(row) for row in sources),
        scanned=scanned,
        rules=tuple(rules),
        strata=tuple(strata),
        companies=tuple(companies),
    )


def write_manifest(universe: UniverseManifest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = universe.model_dump_json(indent=2) + "\n"
    path.write_bytes(text.encode("utf-8"))
    return path


def read_manifest(path: Path) -> UniverseManifest:
    return UniverseManifest.model_validate_json(path.read_bytes())


Member = tuple[zipfile.ZipFile, RawObject, str, str, Callable[[Path], Summary]]


@dataclass
class ExtractReport:
    stored: int = 0
    unchanged: int = 0
    bytes_new: int = 0


def extract(
    archive: RawArchive,
    ciks: Sequence[str],
    facts_row: RawObject,
    submissions_row: RawObject,
    *,
    run_id: str,
    progress: Callable[[int, int], None] | None = None,
) -> ExtractReport:
    """Copy each company's members of the two ZIP files into the raw archive, validated."""
    report = ExtractReport()
    archive.tmp_dir.mkdir(parents=True, exist_ok=True)
    with (
        zipfile.ZipFile(archive.root / facts_row.path) as facts,
        zipfile.ZipFile(archive.root / submissions_row.path) as submissions,
    ):
        for number, cik in enumerate(ciks, start=1):
            main = json.loads(submissions.read(f"CIK{cik}.json"))
            name = f"CIK{cik}.json"
            members: list[Member] = [
                (facts, facts_row, name, f"CIK{cik}", _checker(check_companyfacts, cik)),
                (submissions, submissions_row, name, f"CIK{cik}", _checker(check_submissions, cik)),
            ]
            for page in main["filings"].get("files", []):
                match = PAGE_MEMBER.fullmatch(page["name"])
                if match is None or match[1] != cik:
                    raise ValueError(f"unexpected older-filing page {page['name']!r} for {cik}")
                key = f"CIK{cik}/submissions-{match[2]}"
                members.append(
                    (submissions, submissions_row, page["name"], key, check_submissions_page)
                )
            for source, row, member, key, check in members:
                created, size = _store_member(archive, source, row, member, key, cik, check, run_id)
                if created:
                    report.stored += 1
                    report.bytes_new += size
                else:
                    report.unchanged += 1
            if progress is not None:
                progress(number, len(ciks))
    return report


def _checker(check: Callable[[Path, str], Summary], cik: str) -> Callable[[Path], Summary]:
    return lambda path: check(path, cik)


def _store_member(
    archive: RawArchive,
    source: zipfile.ZipFile,
    row: RawObject,
    member: str,
    key: str,
    cik: str,
    check: Callable[[Path], Summary],
    run_id: str,
) -> tuple[bool, int]:
    part = archive.tmp_dir / f"{uuid.uuid4().hex}.part"
    part.write_bytes(source.read(member))
    try:
        summary = check(part)
    except Exception:
        part.unlink()
        raise

    def describe(sha: str, size: int, path: str) -> RawObject:
        return RawObject.model_validate(
            {
                **row.model_dump(),
                "key": key,
                "cik": cik,
                "url": f"{row.url}#{member}",
                "path": path,
                "sha256": sha,
                "size_bytes": size,
                "file_format": "json",
                "content_length": None,
                "etag": None,
                "run_id": run_id,
                "filing_count": summary.filing_count,
                "latest_filing_id": summary.latest_filing_id,
                "latest_filed": summary.latest_filed,
                "catalog_version": CONTRACTS_VERSION,
            }
        )

    stored, created = archive.store(
        part, dataset_id=row.dataset_id, key=key, file_format="json", describe=describe
    )
    return created, stored.size_bytes


def bulk_rows(archive: RawArchive) -> tuple[RawObject, RawObject]:
    """The latest archived Company Facts and Submissions ZIP files."""
    facts = archive.latest(COMPANYFACTS, "bulk/companyfacts")
    submissions = archive.latest(SUBMISSIONS, "bulk/submissions")
    if facts is None or submissions is None:
        raise ValueError(
            "the bulk files are not archived: run `sec bulk companyfacts-zip` and "
            "`sec bulk submissions-zip` first"
        )
    return facts, submissions
