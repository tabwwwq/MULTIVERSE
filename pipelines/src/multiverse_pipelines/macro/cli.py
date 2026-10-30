"""Commands of the macro pipeline: ``python -m multiverse_pipelines.macro <command>``.

    status          per source: owner decision, FRED key present or not, stored series
    fetch           download one source into var/raw (refused until D-11 / D-12 and the locks)
    build           archived files into var/data/macro/macro.sqlite
    load-synthetic  SYNTHETIC documents into var/data/macro/macro-synthetic.sqlite
    as-of           one series as available at a moment
    qa              series coverage and timestamp QA
    join            macro features joined with the PIT panel at a cutoff, with provenance

Without a key or a decision nothing fails: the sources are reported unavailable, and
their cells in a join say why.
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from multiverse_config import Settings, load_settings
from multiverse_contracts.macro import MacroCell, MacroObservation
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_contracts.sources import DataSource
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.macro import parsers, synthetic
from multiverse_pipelines.macro.fetch import fetch_source, redact_text, unavailable_reason
from multiverse_pipelines.macro.join import macro_join
from multiverse_pipelines.macro.joined import make_joined, write_joined
from multiverse_pipelines.macro.qa import series_qa, write_qa
from multiverse_pipelines.macro.registry import BY_ID, SERIES, SOURCES
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.clock import parse_cutoff, stamp
from multiverse_pipelines.pit.snapshot import make_snapshot
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.errors import IngestionError
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.sec.validate import load_json

ARCHIVE_DIRS = {"fred-alfred": "fred", "ecb-data-portal": "ecb", "world-bank": "worldbank"}
NAMES = {"fred": "fred-alfred", "ecb": "ecb-data-portal", "worldbank": "world-bank"}
BUDGET_BYTES = 20 * 1024 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m multiverse_pipelines.macro",
        description="Macro series with vintages and the as-of join (Stage 13).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="decisions, key and stored series per source")
    fetch = commands.add_parser("fetch", help="download one source (needs the owner's decision)")
    fetch.add_argument("--source", choices=sorted(NAMES), required=True)
    fetch.add_argument("--series", action="append", help="repeatable series id; default: all")
    commands.add_parser("build", help="archived files into the macro store")
    load = commands.add_parser("load-synthetic", help="SYNTHETIC documents into a separate store")
    load.add_argument("--until", default="2026-10-28", help="last publication day")
    for name in ("as-of", "qa", "join"):
        command = commands.add_parser(name)
        command.add_argument("--synthetic", action="store_true", help="use the synthetic store")
        if name == "as-of":
            command.add_argument("--series", required=True)
            command.add_argument("--at", required=True)
        if name == "join":
            command.add_argument("--cutoff", required=True)
            command.add_argument("--quarters", type=int, default=8)
            command.add_argument("--cik", action="append")
    return parser


def _sources() -> dict[str, DataSource]:
    return {s.source_id: s for s in SOURCE_CATALOG.sources if s.source_id in SOURCES}


def _archive(settings: Settings, source_id: str) -> RawArchive:
    return RawArchive(
        settings.raw_dir, budget_bytes=BUDGET_BYTES, source_dir=ARCHIVE_DIRS[source_id]
    )


def _store_path(settings: Settings, synthetic_store: bool) -> Path:
    name = "macro-synthetic.sqlite" if synthetic_store else "macro.sqlite"
    return settings.data_dir / "macro" / name


def unavailable(settings: Settings) -> dict[str, str]:
    return {sid: unavailable_reason(settings, source) for sid, source in _sources().items()}


def build_store(
    settings: Settings, path: Path | None, now: datetime
) -> tuple[MacroStore, dict[str, int]]:
    store = MacroStore.create(path, synthetic=False, built_at=now)
    counts: dict[str, int] = {}
    for source_id in SOURCES:
        archive = _archive(settings, source_id)
        by_key: dict[str, list[RawObject]] = {}
        for row in sorted(archive.objects(), key=lambda r: r.downloaded_at):
            by_key.setdefault(row.key, []).append(row)
        found: list[MacroObservation] = []
        for key, rows in by_key.items():
            newest = archive.root / rows[-1].path
            if source_id == "fred-alfred":
                found += parsers.fred_observations(
                    key, load_json(newest), raw_sha256=rows[-1].sha256
                )
            elif source_id == "ecb-data-portal":
                text = newest.read_text(encoding="utf-8")
                found += parsers.ecb_observations(text, raw_sha256=rows[-1].sha256)
            else:
                # Every archived file of one indicator is a dated snapshot of it.
                snapshots = [
                    parsers.worldbank_snapshot(
                        load_json(archive.root / r.path), raw_sha256=r.sha256
                    )
                    for r in rows
                ]
                found += parsers.worldbank_observations(snapshots)
        store.register(
            s.series_id
            for s in SERIES
            if s.source_id == source_id and any(k in s.series_id for k in by_key)
        )
        counts[source_id] = store.add(found)
    return store, counts


def load_synthetic(path: Path | None, until: date, now: datetime) -> MacroStore:
    store = MacroStore.create(path, synthetic=True, built_at=now)
    store.register(s.series_id for s in SERIES)
    for code, doc in synthetic.fred_documents(until).items():
        store.add(parsers.fred_observations(code, doc, synthetic=True))
    store.add(parsers.ecb_observations(synthetic.ecb_csv(until), synthetic=True))
    for code in synthetic.WB_CODES:
        snapshots = [
            parsers.worldbank_snapshot(doc) for doc in synthetic.worldbank_snapshots(until, code)
        ]
        store.add(parsers.worldbank_observations(snapshots, synthetic=True))
    return store


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    now = datetime.now(UTC)
    try:
        return _run(args, settings, now)
    except (ValueError, IngestionError) as exc:
        print(f"refused: {redact_text(str(exc))}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace, settings: Settings, now: datetime) -> int:
    reasons = unavailable(settings)
    if args.command == "status":
        path = _store_path(settings, False)
        stored = set(MacroStore.open(path).series()) if path.exists() else set()
        for source_id, source in _sources().items():
            mine = [s for s in SERIES if s.source_id == source_id]
            have = sum(s.series_id in stored for s in mine)
            key = ""
            if source_id == "fred-alfred":
                key = f", key {'set' if settings.fred_api_key else 'not set'}"
            print(
                f"{source_id:<16} decision {source.download.status}{key}; "
                f"{have} of {len(mine)} series stored"
            )
            if have < len(mine):
                print(f"{'':<16} {reasons[source_id]}")
        return 0
    if args.command == "fetch":
        source = _sources()[NAMES[args.source]]
        archive = _archive(settings, source.source_id)
        report = fetch_source(
            settings,
            source,
            archive,
            run_id=now.strftime("%Y%m%dT%H%M%SZ"),
            catalog_version=CONTRACTS_VERSION,
            series_ids=args.series,
        )
        print(
            f"{report.requests} requests, {len(report.stored)} new files, "
            f"{len(report.unchanged)} unchanged"
        )
        for line in report.skipped:
            print(f"skipped {line}")
        return 0
    if args.command == "build":
        store, counts = build_store(settings, _store_path(settings, False), now)
        for source_id, count in counts.items():
            print(
                f"{source_id:<16} {count:>7} observations"
                + ("" if count else f"  ({reasons[source_id]})")
            )
        store.close()
        return 0
    if args.command == "load-synthetic":
        store = load_synthetic(_store_path(settings, True), date.fromisoformat(args.until), now)
        print(f"SYNTHETIC store: {len(store.series())} series into {_store_path(settings, True)}")
        store.close()
        return 0
    store = MacroStore.open(_store_path(settings, args.synthetic))
    try:
        return _query(args, settings, store, reasons, now)
    finally:
        store.close()


def _query(
    args: argparse.Namespace,
    settings: Settings,
    store: MacroStore,
    reasons: dict[str, str],
    now: datetime,
) -> int:
    label = " (SYNTHETIC)" if store.synthetic else ""
    if args.command == "as-of":
        if args.series not in BY_ID:
            raise ValueError(f"{args.series} is not registered")
        at = parse_cutoff(args.at)
        rows = store.as_of(args.series, at)
        print(f"{args.series} as available at {stamp(at)}{label}")
        for observation in list(rows.values())[-12:]:
            print(
                f"{observation.period_start} {observation.value or '-':>12} published "
                f"{stamp(observation.available_from)} ({observation.basis.value})"
            )
        print(f"{len(rows)} periods")
        return 0
    if args.command == "qa":
        report = series_qa(store, SERIES)
        name = "qa-synthetic" if store.synthetic else "qa"
        folder = write_qa(
            report,
            settings.data_dir / "macro" / name,
            synthetic=store.synthetic,
            unavailable=reasons,
        )
        print(f"wrote {folder}{label}")
        return 0
    cutoff = parse_cutoff(args.cutoff)
    warehouse = Warehouse.open(settings.data_dir / "pit" / "warehouse.sqlite")
    try:
        ciks = args.cik or warehouse.ciks()
        snapshot = make_snapshot(
            warehouse,
            ciks,
            cutoff,
            cutoff_label=args.cutoff,
            created_at=now,
            quarters=args.quarters,
        )
    finally:
        warehouse.close()
    cells = macro_join(snapshot.panel.cells, store, SERIES, cutoff, unavailable=reasons)
    joined = make_joined(snapshot, cells, synthetic_store=store.synthetic, created_at=now)
    root = settings.data_dir / "macro" / ("joined-synthetic" if store.synthetic else "joined")
    folder = write_joined(joined, cells, root)
    states = ", ".join(f"{k} {v}" for k, v in sorted(_count(cells).items()))
    print(f"{joined.join_id}{label}: {len(cells)} macro cells ({states})")
    print(f"wrote {folder}")
    return 0


def _count(cells: Sequence[MacroCell]) -> dict[str, int]:
    found: dict[str, int] = {}
    for cell in cells:
        found[cell.state.value] = found.get(cell.state.value, 0) + 1
    return found
