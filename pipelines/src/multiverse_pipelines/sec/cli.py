"""Commands of SEC raw ingestion: ``python -m multiverse_pipelines.sec <command>``.

``status``, ``verify`` and ``coverage`` never touch the network. ``sample``, ``probe`` and
``bulk`` pass the three locks of ``gate.py`` first; ``bulk`` also needs ``--max-mb``.
Exit codes: 0 done, 1 some files failed, 2 refused or aborted, 3 the archive has problems.
"""

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

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

SOURCE_ID = "sec-edgar"
MB = 1024 * 1024


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
        return _network(args, settings, archive, transport)
    except (IngestionError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
