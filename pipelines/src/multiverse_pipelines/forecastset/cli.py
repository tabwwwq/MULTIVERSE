"""The forecasting dataset: ``python -m multiverse_pipelines.forecastset build``.

Reads the PIT warehouse, the universe file and the real macro store; writes
``var/data/forecast/<dataset id>/`` (never committed): ``dataset.csv`` and
``manifest.json`` (``ForecastDatasetManifest``). The id is the SHA-256 of the CSV.
"""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from multiverse_config import load_settings
from multiverse_contracts.forecasting import ForecastDatasetManifest, ForecastTarget
from multiverse_contracts.pit import KnowledgeView
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.audit.examples import origins
from multiverse_pipelines.forecastset.build import (
    FEATURES,
    FIRST_ORIGIN,
    HORIZONS,
    MACRO,
    build_rows,
    kept,
    macro_features,
    sha256_text,
    target_counts,
    to_csv,
    write_rows,
)
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.clock import eastern_date, from_stamp, parse_cutoff
from multiverse_pipelines.pit.panel import quarter_ends
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.universe import division, read_manifest

WORKERS = max(1, (os.cpu_count() or 1) - 4)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m multiverse_pipelines.forecastset")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="features and targets for every company origin")
    build.add_argument("--universe", type=Path, required=True)
    build.add_argument("--cutoff", default="2026-10-28", help="data cutoff (end of day, ET)")
    build.add_argument("--workers", type=int, default=WORKERS)
    build.add_argument("--out", type=Path, help="default: <data dir>/forecast")
    return parser


def _progress(number: int, total: int) -> None:
    if number % 100 == 0 or number == total:
        print(f"companies {number}/{total}", file=sys.stderr, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    db_path = settings.data_dir / "pit" / "warehouse.sqlite"
    try:
        warehouse = Warehouse.open(db_path)
        built_at = from_stamp(warehouse.meta()["built_at"])
        warehouse.close()
        universe = read_manifest(args.universe)
        data_cutoff = parse_cutoff(args.cutoff)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    last = quarter_ends(eastern_date(data_cutoff), 1)[0]
    when = origins(FIRST_ORIGIN, last)
    divisions = {c.cik: division(c.sic)[0] for c in universe.companies}
    macro_path = settings.data_dir / "macro" / "macro.sqlite"
    store = MacroStore.open(macro_path) if macro_path.exists() else None
    macro = macro_features(store, when)
    if store is not None:
        store.close()
    rows = build_rows(db_path, divisions, when, data_cutoff, args.workers, _progress)
    text = to_csv(rows, macro)
    digest = sha256_text(text)
    first, final = kept(when, rows)
    manifest = ForecastDatasetManifest(
        dataset_id=f"fds-{eastern_date(data_cutoff):%Y%m%d}-{digest[:12]}",
        sha256=digest,
        universe_id=universe.universe_id,
        pit_built_at=built_at,
        data_cutoff=data_cutoff,
        view=KnowledgeView.VINTAGE,
        first_origin=first,
        last_origin=final,
        horizons=HORIZONS,
        targets=tuple(ForecastTarget),
        features=FEATURES,
        macro_series=tuple(series for _, series, _ in MACRO) if store is not None else (),
        rows=len(rows),
        companies=len({r["cik"] for r in rows}),
        target_counts=tuple(target_counts(rows)),
        contracts_version=CONTRACTS_VERSION,
        created_at=datetime.now(UTC),
    )
    folder = (args.out or settings.data_dir / "forecast") / manifest.dataset_id
    write_rows(text, folder)
    (folder / "manifest.json").write_bytes(
        (json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n").encode("utf-8")
    )
    print(f"{manifest.dataset_id}: {manifest.rows} rows, {manifest.companies} companies")
    for count in manifest.target_counts:
        print(
            f"{count.target.value:<17} h={count.horizon:<2} {count.defined:>6} defined "
            f"{count.undefined:>5} undefined"
        )
    print(f"wrote {folder}")
    return 0
