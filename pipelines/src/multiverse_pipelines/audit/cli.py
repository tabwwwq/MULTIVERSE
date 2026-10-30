"""Gate B: ``python -m multiverse_pipelines.audit run [--cutoff DATE]``.

Reads the PIT warehouse and raw archive of the SEC sample, the macro stores and the
manual reconciliation file; writes the manifest, examples, data card and coverage report
into ``var/data/gate/``. Exit code 0 when the gate passes, 3 when it is blocked (the
report is written either way), 2 when it cannot run.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from multiverse_config import load_settings
from multiverse_contracts.quality import GateVerdict
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_pipelines.audit.report import write_gate
from multiverse_pipelines.audit.run import run_gate
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.archive import RawArchive

RECONCILIATION = Path("data/reconciliation/stage-14-manual.json")
LEAKAGE_CUTOFFS = ("2013-06-30", "2019-12-31", "2025-12-31")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m multiverse_pipelines.audit", description=__doc__
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="every check, the counts, manifest and data card")
    run.add_argument("--cutoff", default="2026-10-28", help="data cutoff (end of day, US Eastern)")
    run.add_argument(
        "--leakage-cutoff", action="append", help=f"default: {', '.join(LEAKAGE_CUTOFFS)}"
    )
    run.add_argument("--reconciliation", type=Path, default=RECONCILIATION)
    run.add_argument("--out", type=Path)
    return parser


def _store(path: Path) -> MacroStore | None:
    return MacroStore.open(path) if path.exists() else None


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    now = datetime.now(UTC)
    try:
        warehouse = Warehouse.open(settings.data_dir / "pit" / "warehouse.sqlite")
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    archive = RawArchive(settings.raw_dir, budget_bytes=settings.raw_budget_mb * 1024 * 1024)
    names = {c.cik: c.name for c in SOURCE_CATALOG.candidates}
    candidates = {c.cik: c for c in SOURCE_CATALOG.candidates}
    real = _store(settings.data_dir / "macro" / "macro.sqlite")
    synthetic = _store(settings.data_dir / "macro" / "macro-synthetic.sqlite")
    try:
        result = run_gate(
            warehouse=warehouse,
            archive=archive,
            ciks=warehouse.ciks(),
            names=names,
            candidates=candidates,
            data_cutoff_label=args.cutoff,
            reconciliation=args.reconciliation,
            real_macro=real,
            synthetic_macro=synthetic,
            leakage_cutoffs=args.leakage_cutoff or LEAKAGE_CUTOFFS,
            now=now,
            workers=os.cpu_count() or 1,
        )
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    finally:
        warehouse.close()
        for store in (real, synthetic):
            if store is not None:
                store.close()
    folder = write_gate(
        args.out or settings.data_dir / "gate",
        result.manifest,
        result.data,
        result.examples,
        SOURCE_CATALOG.sectors,
        result.usability,
    )
    manifest = result.manifest
    for check in manifest.checks:
        print(f"{check.status.value:<8} {check.title}: {check.summary}")
    print(f"{manifest.dataset_id}: {manifest.verdict.value}")
    print(f"wrote {folder}")
    return 3 if manifest.verdict is GateVerdict.BLOCKED else 0
