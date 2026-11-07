"""Commands of SEC raw ingestion: ``python -m multiverse_pipelines.sec <command>``.

``status``, ``verify``, ``coverage`` and ``universe`` never touch the network. ``sample``,
``probe`` and ``bulk`` pass the three locks of ``gate.py`` first; ``bulk`` also needs
``--max-mb``. ``universe`` draws the study universe from the archived bulk files and copies
the chosen companies' files out of them; it needs the owner's bulk approval (D-10).
Exit codes: 0 done, 1 some files failed, 2 refused or aborted, 3 the archive has problems.
"""

import argparse
import json
import sys
import uuid
import zipfile
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx

from multiverse_config import Settings, load_settings
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_contracts.sources import DataSource, DownloadScope
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.client import SecClient
from multiverse_pipelines.sec.coverage import build_coverage, to_markdown
from multiverse_pipelines.sec.errors import IngestionError, PermissionRefusedError
from multiverse_pipelines.sec.gate import check_user_agent, require_permission
from multiverse_pipelines.sec.ingest import BULK_TARGETS, SecIngestor
from multiverse_pipelines.sec.models import RunManifest, RunStatus
from multiverse_pipelines.sec.top import (
    SIZE,
    corrected,
    listing_from,
    load_floats,
    ranked,
    read_exchange_list,
    save_floats,
    scan_floats,
    top_manifest,
    with_exchange_list,
)
from multiverse_pipelines.sec.universe import (
    bulk_rows,
    eligibility,
    excluded_ranges,
    extract,
    manifest,
    read_manifest,
    scan,
    select,
    write_manifest,
)

SOURCE_ID = "sec-edgar"
MB = 1024 * 1024
UNIVERSE_DIR = Path("data/universe")


def sec_source() -> DataSource:
    return next(s for s in SOURCE_CATALOG.sources if s.source_id == SOURCE_ID)


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def archive_for(settings: Settings) -> RawArchive:
    return RawArchive(settings.raw_dir, budget_bytes=settings.raw_budget_mb * MB)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m multiverse_pipelines.sec",
        description="SEC raw ingestion into an immutable local archive (Stage 10).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="settings, owner decision and archive use; no network")
    sample = commands.add_parser("sample", help="submissions and company facts of a few CIKs")
    sample.add_argument(
        "--cik", action="append", help="repeatable; default: the ten catalog candidates"
    )
    sample.add_argument(
        "--max-age-hours",
        type=float,
        default=12.0,
        help="reuse files the SEC confirmed within this time without asking again",
    )
    probe = commands.add_parser("probe", help="HEAD request for the size of one bulk file")
    probe.add_argument("target", choices=BULK_TARGETS)
    probe.add_argument("--quarter", help="for fsds, for example 2024q1")
    universe = commands.add_parser(
        "universe", help="draw the study universe from the archived bulk files (no network)"
    )
    universe.add_argument("--size", type=int, default=1000)
    universe.add_argument("--seed", type=int, default=20261030)
    universe.add_argument("--out", type=Path, help=f"default: {UNIVERSE_DIR}/<universe id>.json")
    universe.add_argument(
        "--no-extract", action="store_true", help="choose only; do not copy files out"
    )
    top = commands.add_parser(
        "top", help="the largest filers by public float, from the archived bulk files (no network)"
    )
    top.add_argument("--size", type=int, default=SIZE)
    top.add_argument("--day", help="the day of the ranking; default: today", default=None)
    top.add_argument("--also", type=Path, help="a universe to add, for training only")
    top.add_argument("--out", type=Path, help=f"default: {UNIVERSE_DIR}/sec-top<size>-<day>.json")
    bulk = commands.add_parser("bulk", help="one bulk ZIP; needs the owner's bulk approval")
    bulk.add_argument("target", choices=BULK_TARGETS)
    bulk.add_argument("--quarter", help="for fsds, for example 2024q1")
    bulk.add_argument("--max-mb", type=int, required=True, help="refuse larger files")
    commands.add_parser("verify", help="re-hash every archived file; no network")
    coverage = commands.add_parser("coverage", help="what the archived sample holds; no network")
    coverage.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    return parser


def _status(settings: Settings, archive: RawArchive) -> int:
    source = sec_source()
    try:
        check_user_agent(settings.sec_user_agent)
        agent = "set, with a contact email"
    except PermissionRefusedError:
        agent = "missing or without a contact email"
    decision = source.download
    print(f"network downloads   {'on' if settings.allow_network_downloads else 'off'}")
    print(f"User-Agent          {agent}")
    print(f"owner decision      {decision.status} ({decision.scope}) on {decision.decided_on}")
    print(f"request rate        {source.rate_limit.chosen_requests_per_second} per second")
    used = archive.usage_bytes()
    print(f"raw archive         {archive.root} ({used / MB:.1f} of {settings.raw_budget_mb} MB)")
    counts: dict[str, int] = {}
    for row in archive.objects():
        counts[row.dataset_id] = counts.get(row.dataset_id, 0) + 1
    for dataset_id, count in sorted(counts.items()):
        print(f"  {dataset_id:<36}{count} files")
    return 0


def _report(manifest: RunManifest) -> int:
    for record in manifest.records:
        size = f"{record.size_bytes / MB:8.2f} MB" if record.size_bytes is not None else " " * 11
        if record.outcome == "probed" and record.content_length is not None:
            size = f"{record.content_length / MB:8.1f} MB"
        detail = f"  {record.error}" if record.error else ""
        print(f"{record.outcome:<17}{size}  {record.dataset_id} {record.key}{detail}")
    new_mb = manifest.bytes_new / MB
    print(
        f"run {manifest.run_id}: {manifest.status}, {manifest.requests} requests, "
        f"{new_mb:.2f} MB new" + (f" - {manifest.message}" if manifest.message else "")
    )
    return {RunStatus.COMPLETED: 0, RunStatus.FAILED: 1, RunStatus.ABORTED: 2}[manifest.status]


def _network(
    args: argparse.Namespace,
    settings: Settings,
    archive: RawArchive,
    transport: httpx.BaseTransport | None,
) -> int:
    source = sec_source()
    scope = DownloadScope.BULK if args.command == "bulk" else DownloadScope.SAMPLE
    user_agent = require_permission(settings, source, scope)
    with SecClient(
        user_agent=user_agent,
        allowed_hosts=source.official_hosts,
        rate_per_second=Decimal(source.rate_limit.chosen_requests_per_second),
        tmp_dir=archive.tmp_dir,
        transport=transport,
    ) as client:
        ingestor = SecIngestor(
            client=client,
            archive=archive,
            source=source,
            catalog_version=SOURCE_CATALOG.contracts_version,
            run_id=new_run_id(),
            max_age=timedelta(hours=getattr(args, "max_age_hours", 12.0)),
        )
        if args.command == "sample":
            ciks: Sequence[str] = args.cik or [c.cik for c in SOURCE_CATALOG.candidates]
            return _report(ingestor.sample(ciks))
        target = ingestor.connectors.bulk(args.target, args.quarter)
        if args.command == "probe":
            return _report(ingestor.probe(target))
        return _report(ingestor.bulk(target, max_bytes=args.max_mb * MB))


def _progress(label: str) -> Callable[[int, int], None]:
    def show(number: int, total: int) -> None:
        if number % 1000 == 0 or number == total:
            print(f"{label} {number}/{total}", file=sys.stderr, flush=True)

    return show


def _top(args: argparse.Namespace, archive: RawArchive) -> int:
    """Ranks every filer by its float and copies the chosen companies into the archive."""
    day = date.fromisoformat(args.day) if args.day else date.today()
    facts_row, submissions_row = bulk_rows(archive)
    facts_zip = archive.root / facts_row.path
    submissions_zip = archive.root / submissions_row.path
    cache = archive.root.parent / "data" / f"top-floats-{facts_row.sha256[:12]}.json"
    if cache.exists():
        floats = load_floats(cache)
    else:
        floats = scan_floats(facts_zip, day, _progress("floats"))
        save_floats(floats, cache)
    plausible = [item for item in map(corrected, floats) if item is not None]
    listed = read_exchange_list(archive.root / "sec" / "company_tickers_exchange.json")
    with zipfile.ZipFile(submissions_zip) as submissions:
        listings = {}
        for number, item in enumerate(sorted(plausible, key=lambda c: -c.public_float)):
            if number >= args.size * 6:
                break
            found = listing_from(submissions, item.cik)
            if found is not None:
                listings[item.cik] = with_exchange_list(found, listed, item.cik)
    chosen = ranked(plausible, listings, args.size)
    universe = top_manifest(
        universe_id=f"sec-top{args.size}-{day:%Y%m%d}",
        chosen=chosen,
        listings=listings,
        scanned=len(floats),
        plausible=len(plausible),
        rows=(facts_row, submissions_row),
    )
    path = write_manifest(universe, args.out or UNIVERSE_DIR / f"{universe.universe_id}.json")
    ciks = [company.cik for company in universe.companies]
    if args.also:
        ciks += [c.cik for c in read_manifest(args.also).companies if c.cik not in set(ciks)]
    report = extract(
        archive,
        ciks,
        facts_row,
        submissions_row,
        run_id=new_run_id(),
        progress=_progress("extract"),
    )
    print(
        f"{path}: {len(universe.companies)} companies, largest {chosen[0].name}, "
        f"{report.stored} files stored, {report.unchanged} unchanged"
    )
    return 0


def _universe(args: argparse.Namespace, archive: RawArchive) -> int:
    source = sec_source()
    decision = source.download
    if decision.status != "approved" or decision.scope != DownloadScope.BULK:
        raise PermissionRefusedError(
            "the universe is drawn from the bulk files, which need the owner's bulk approval"
        )
    facts_row, submissions_row = bulk_rows(archive)
    excluded = excluded_ranges(SOURCE_CATALOG.sectors)
    scanned = scan(
        archive.root / facts_row.path,
        archive.root / submissions_row.path,
        excluded,
        _progress("scanned"),
    )
    rules, eligible = eligibility(scanned, excluded)
    required = [c.cik for c in SOURCE_CATALOG.candidates]
    strata, chosen = select(eligible, args.size, args.seed, required)
    universe_id = f"sec-{args.size}-{args.seed}"
    universe = manifest(
        universe_id=universe_id,
        seed=args.seed,
        size=args.size,
        created_at=datetime.now(UTC),
        sources=(facts_row, submissions_row),
        scanned=len(scanned),
        rules=rules,
        strata=strata,
        chosen=chosen,
        required=required,
    )
    path = write_manifest(universe, args.out or UNIVERSE_DIR / f"{universe_id}.json")
    print(f"{len(scanned)} companies with Company Facts")
    for rule in rules:
        print(f"{rule.remaining:>7}  {rule.rule}")
    for stratum in strata:
        print(
            f"{stratum.division} {stratum.title:<44} eligible {stratum.eligible:>5} "
            f"chosen {stratum.selected:>4}"
        )
    print(f"wrote {path}")
    if args.no_extract:
        return 0
    report = extract(
        archive,
        [c.cik for c in chosen],
        facts_row,
        submissions_row,
        run_id=new_run_id(),
        progress=_progress("extracted"),
    )
    print(
        f"{report.stored} files copied out of the ZIP files ({report.bytes_new / MB:.1f} MB), "
        f"{report.unchanged} already archived"
    )
    return 0


def main(argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    """``transport`` replaces the network in tests; commands always run with ``None``."""
    args = _parser().parse_args(argv)
    settings = load_settings()
    archive = archive_for(settings)
    try:
        if args.command == "status":
            return _status(settings, archive)
        if args.command == "verify":
            report = archive.verify()
            for problem in report.problems:
                print(problem)
            print(f"{report.checked} files checked, {len(report.problems)} problems")
            return 3 if report.problems else 0
        if args.command == "coverage":
            rows = build_coverage(archive, SOURCE_CATALOG.candidates)
            if args.json:
                print(json.dumps([row.model_dump(mode="json") for row in rows], indent=2))
            else:
                print(to_markdown(rows), end="")
            return 0
        if args.command == "universe":
            return _universe(args, archive)
        if args.command == "top":
            return _top(args, archive)
        return _network(args, settings, archive, transport)
    except (IngestionError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
