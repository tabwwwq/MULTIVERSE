"""Commands of the point-in-time warehouse: ``python -m multiverse_pipelines.pit <command>``.

Every command reads the local raw archive of Stage 10 or the warehouse built from it;
none touches the network.

    build           all archived candidates (or --cik) into var/data/pit/warehouse.sqlite
    as-of           one company and metric as known at a moment
    history         every answer one period had: its corrections over time
    entity          name, ticker, exchange and SIC code as known at a moment
    snapshot        the as-of panel at a cutoff, hashed, with features and lineage
    coverage        the coverage dashboard at a cutoff (HTML, Markdown, JSON)
    alerts          broken chronology alerts
    leakage-check   rebuild from what was public at a cutoff and compare the snapshots
"""

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from multiverse_config import load_settings
from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.normalized import FiscalPeriod, Revision
from multiverse_contracts.pit import EntityAttributeName, KnowledgeView, PitValue
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_pipelines.pit.build import build_warehouse
from multiverse_pipelines.pit.clock import eastern_date, parse_cutoff, stamp
from multiverse_pipelines.pit.coverage import (
    Coverage,
    coverage_over_time,
    revision_stats,
    write_coverage,
)
from multiverse_pipelines.pit.filings import attribute_as_of
from multiverse_pipelines.pit.snapshot import make_snapshot, write_snapshot
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.cik import cik10

VIEWS = [view.value for view in KnowledgeView]
WORKERS = os.cpu_count() or 1
PIT_VIEWS = [KnowledgeView.VINTAGE.value, KnowledgeView.ORIGINAL.value]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m multiverse_pipelines.pit",
        description="Point-in-time warehouse over the archived SEC sample (Stage 12).",
    )
    parser.add_argument("--db", type=Path, help="default: <data dir>/pit/warehouse.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build the warehouse from the raw archive")
    build.add_argument("--cik", action="append", help="repeatable; default: catalog candidates")
    as_of = commands.add_parser("as-of", help="one company and metric as known at a moment")
    as_of.add_argument("--cik", required=True)
    as_of.add_argument("--metric", required=True)
    as_of.add_argument("--at", required=True, help="a date (end of day, US Eastern) or a time")
    as_of.add_argument("--view", choices=VIEWS, default="vintage")
    as_of.add_argument("--fiscal-year", type=int)
    history = commands.add_parser("history", help="every answer one period had")
    history.add_argument("--cik", required=True)
    history.add_argument("--metric", required=True)
    history.add_argument("--fiscal-year", type=int, required=True)
    history.add_argument("--period", choices=[p.value for p in FiscalPeriod], required=True)
    history.add_argument("--revision", choices=[r.value for r in Revision], default="latest")
    entity = commands.add_parser("entity", help="identity of a company as known at a moment")
    entity.add_argument("--cik", required=True)
    entity.add_argument("--at", required=True)
    for name in ("snapshot", "coverage", "leakage-check"):
        command = commands.add_parser(name)
        command.add_argument("--cutoff", required=True)
        command.add_argument("--quarters", type=int, default=20)
        command.add_argument("--view", choices=PIT_VIEWS, default="vintage")
        command.add_argument("--cik", action="append")
        command.add_argument("--out", type=Path)
    alerts = commands.add_parser("alerts", help="broken chronology alerts")
    alerts.add_argument("--cik", action="append")
    alerts.add_argument("--severity", choices=[s.value for s in QualitySeverity])
    return parser


def _value_line(item: PitValue) -> str:
    row = item.value
    shown = row.value if row.value is not None else f"- ({row.missing_reason})"
    until = stamp(item.known_to) if item.known_to else "now"
    method = row.method.value if row.method else ""
    flags = ",".join(row.flags)
    return (
        f"FY{row.fiscal_year} {row.fiscal_period.value:<2} {row.period_end} {shown:>16} "
        f"{method:<24} {row.accession or '':<20} {stamp(item.known_from)} .. {until} "
        f"{item.change.value} {flags}"
    ).rstrip()


def _names() -> dict[str, str]:
    return {c.cik: c.name for c in SOURCE_CATALOG.candidates}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    db_path = args.db or settings.data_dir / "pit" / "warehouse.sqlite"
    archive = RawArchive(settings.raw_dir, budget_bytes=settings.raw_budget_mb * 1024 * 1024)
    candidates = [c.cik for c in SOURCE_CATALOG.candidates]
    now = datetime.now(UTC)
    try:
        if args.command == "build":
            ciks = [cik10(c) for c in (args.cik or candidates)]
            warehouse = build_warehouse(archive, ciks, db_path, built_at=now, workers=WORKERS)
            names = _names()
            for cik, (points, intervals, estimates) in warehouse.counts().items():
                alerts = warehouse.alerts([cik])
                print(
                    f"{cik} {names.get(cik, ''):<34} {points:>3} knowledge points "
                    f"{intervals:>7} value intervals {estimates:>3} estimates left out "
                    f"{len(alerts):>3} alerts"
                )
            print(f"wrote {db_path}")
            warehouse.close()
            return 0
        if args.command == "leakage-check":
            return _leakage_check(args, archive, db_path, candidates, now)
        warehouse = Warehouse.open(db_path)
        try:
            return _query(args, warehouse, settings.data_dir, candidates, now)
        finally:
            warehouse.close()
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _query(
    args: argparse.Namespace,
    warehouse: Warehouse,
    data_dir: Path,
    candidates: list[str],
    now: datetime,
) -> int:
    if args.command == "as-of":
        at = parse_cutoff(args.at)
        rows = warehouse.as_of(
            args.cik,
            at,
            view=KnowledgeView(args.view),
            metric=args.metric,
            fiscal_year=args.fiscal_year,
        )
        print(f"{cik10(args.cik)} {args.metric} as known at {stamp(at)} ({args.view} view)")
        for item in rows:
            print(_value_line(item))
        print(f"{len(rows)} periods")
        return 0
    if args.command == "history":
        rows = warehouse.history(
            args.cik,
            args.metric,
            args.fiscal_year,
            FiscalPeriod(args.period),
            Revision(args.revision),
        )
        for item in rows:
            print(_value_line(item))
        return 0
    if args.command == "entity":
        at = parse_cutoff(args.at)
        records = warehouse.attributes([args.cik])
        for attribute in EntityAttributeName:
            values, reason = attribute_as_of(records, args.cik, attribute, at)
            print(f"{attribute.value:<9} {', '.join(values) or '-'} {reason or ''}".rstrip())
        gone = warehouse.filings(args.cik).deregistered(at)
        print(f"status    {'deregistration filed: ' + gone.form if gone else 'reporting'}")
        return 0
    if args.command == "alerts":
        found = warehouse.alerts(args.cik)
        if args.severity:
            found = [a for a in found if a.severity.value == args.severity]
        for alert in found:
            print(f"{alert.cik} {alert.severity.value:<8} {alert.kind.value:<28} {alert.detail}")
        print(f"{len(found)} alerts")
        return 0
    cutoff = parse_cutoff(args.cutoff)
    if cutoff > now:
        raise ValueError(f"cutoff {args.cutoff} is in the future")
    ciks = [cik10(c) for c in (args.cik or warehouse.ciks())]
    view = KnowledgeView(args.view)
    snapshot = make_snapshot(
        warehouse,
        ciks,
        cutoff,
        cutoff_label=args.cutoff,
        created_at=now,
        view=view,
        quarters=args.quarters,
    )
    if args.command == "snapshot":
        folder = write_snapshot(snapshot, warehouse, args.out or data_dir / "pit" / "snapshots")
        manifest = snapshot.manifest
        counts = ", ".join(f"{c.state.value} {c.cells}" for c in manifest.state_counts)
        print(f"{manifest.snapshot_id} sha256 {manifest.sha256}")
        print(f"{manifest.cells} cells: {counts}")
        print(f"wrote {folder}")
        return 0
    names = {cik: name for cik, name in _names().items() if cik in ciks}
    report = Coverage(
        cutoff_label=args.cutoff,
        cutoff=cutoff,
        view=view,
        quarters=args.quarters,
        names=names,
        cells=snapshot.panel.cells,
        over_time=coverage_over_time(warehouse, ciks, eastern_date(cutoff), view, 8),
        revisions=revision_stats(warehouse, ciks),
        alerts=warehouse.alerts(ciks),
    )
    folder = write_coverage(
        report, args.out or data_dir / "pit" / "coverage", snapshot_id=snapshot.manifest.snapshot_id
    )
    print(f"wrote {folder}")
    return 0


def _leakage_check(
    args: argparse.Namespace,
    archive: RawArchive,
    db_path: Path,
    candidates: list[str],
    now: datetime,
) -> int:
    cutoff = parse_cutoff(args.cutoff)
    ciks = [cik10(c) for c in (args.cik or candidates)]
    view = KnowledgeView(args.view)
    full = Warehouse.open(db_path)
    truncated = build_warehouse(archive, ciks, None, built_at=now, known_by=cutoff, workers=WORKERS)
    try:
        a, b = (
            make_snapshot(
                source,
                ciks,
                cutoff,
                cutoff_label=args.cutoff,
                created_at=now,
                view=view,
                quarters=args.quarters,
            )
            for source in (full, truncated)
        )
    finally:
        full.close()
        truncated.close()
    same = a.body == b.body
    print(f"full archive:              {a.manifest.snapshot_id}")
    print(f"only what was public then: {b.manifest.snapshot_id}")
    print("identical: yes" if same else "identical: NO, a later filing changed the snapshot")
    return 0 if same else 1
