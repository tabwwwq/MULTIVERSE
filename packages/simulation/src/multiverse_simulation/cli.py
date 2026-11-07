"""Build a case and run it from the command line.

python -m multiverse_simulation companies --universe <file> --db <file> --dataset <folder> ...
python -m multiverse_simulation run --case <file> --decision <file> --paths 10000 --out <file>
python -m multiverse_simulation report --case <file> --decision <file> --report <file> --out <dir>
python -m multiverse_simulation replay --manifest <dir>/manifest.json --case <file>
"""

import argparse
import json
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

from multiverse_config import load_settings
from multiverse_contracts.decisions import DECISION_MODELS, DecisionModel
from multiverse_contracts.simulation import (
    SensitivityRow,
    SimulationCase,
    SimulationReport,
    SimulationSettings,
)
from multiverse_contracts.valuation import StudioInputs
from multiverse_simulation.run import ALTERNATE, METRICS, RISKS, Answer, Frame, simulate
from multiverse_simulation.studio import build_studio
from multiverse_simulation.summary import build_report, ev_change, money

SENSITIVITY_PATHS = 1000
GDP_SERIES = "wb:USA.NY.GDP.MKTP.KD.ZG"
VARIANTS: tuple[tuple[str, str, dict[str, object]], ...] = (
    ("reference", "As run", {}),
    ("short_blocks", "Mean block of 2 quarters", {"mean_block_quarters": 2.0}),
    ("long_blocks", "Mean block of 8 quarters", {"mean_block_quarters": 8.0}),
    ("larger_shocks", "All shocks 25% larger", {"shock_scale": 1.25}),
    ("macro_locked", "Macro columns locked", {"lock_macro": True}),
)


def code_version() -> str:
    try:
        found = subprocess.run(
            ["git", "describe", "--always", "--dirty"],  # noqa: S607 (fixed arguments, no input)
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unversioned"
    return found.stdout.strip() or "unversioned"


def write(path: Path, text: str) -> None:
    """The same bytes on every system: these files are committed."""
    path.write_bytes(text.encode("utf-8") + b"\n")


def load_decision(path: Path) -> DecisionModel:
    payload = path.read_text(encoding="utf-8")
    model = DECISION_MODELS[json.loads(payload)["type"]]
    return model.model_validate_json(payload)  # type: ignore[return-value]


def _sensitivity_row(
    variant: tuple[str, str, dict[str, object]],
    case: SimulationCase,
    decision: DecisionModel,
    settings: SimulationSettings,
) -> SensitivityRow:
    name, label, changes = variant
    paths = min(settings.paths, SENSITIVITY_PATHS)
    changed = settings.model_copy(update={"paths": paths} | changes)
    frame: Frame = simulate(case, decision, changed)[0]
    ebitda = frame.metrics[ALTERNATE, :, -1, METRICS.index("ebitda")]
    low, middle, high = np.nanquantile(ebitda, (0.1, 0.5, 0.9))
    covenant = frame.risks[ALTERNATE, :, RISKS.index("covenant_breach")].mean()
    change = float(np.nanquantile(ev_change(frame), 0.5))
    return SensitivityRow(
        variant=name,
        label=label,
        paths=paths,
        ebitda_p10=money(float(low)),
        ebitda_p50=money(float(middle)),
        ebitda_p90=money(float(high)),
        ev_change_p50=money(change),
        covenant_probability=round(float(covenant), 5),
    )


def run_file(args: argparse.Namespace) -> int:
    case = SimulationCase.model_validate_json(Path(args.case).read_bytes())
    decision = load_decision(Path(args.decision))
    settings = SimulationSettings(paths=args.paths, seed=args.seed, batch_paths=args.batch)
    started = time.perf_counter()

    def progress(frame: Frame) -> Answer:
        print(f"[{100 * frame.done // settings.paths:3d}%] {frame.done} paths", flush=True)
        return "continue"

    frame, _ = simulate(case, decision, settings, on_batch=progress)
    seconds = time.perf_counter() - started
    rows: tuple[SensitivityRow, ...] = ()
    if args.sensitivity:
        rows = tuple(_sensitivity_row(item, case, decision, settings) for item in VARIANTS)
    report = build_report(
        case,
        decision,
        settings,
        frame,
        code_version=code_version(),
        created_at=datetime.now(UTC),
        seconds=seconds,
        sensitivity=rows,
    )
    write(Path(args.out), report.model_dump_json(indent=2))
    print(f"{report.manifest.report_id}: {settings.paths} paths in {seconds:.1f} s -> {args.out}")
    return 0


def companies_file(args: argparse.Namespace) -> int:
    """Files of the screens and cases of the worker, for a ranked universe."""
    # Heavy imports stay here: a run needs neither the warehouse nor scikit-learn.
    from multiverse_contracts.forecasting import LiveForecast
    from multiverse_forecast.data import load
    from multiverse_pipelines.macro.store import MacroStore
    from multiverse_pipelines.pit.warehouse import Warehouse
    from multiverse_pipelines.sec.universe import read_manifest
    from multiverse_simulation.companies import export

    settings = load_settings()

    def show(number: int, total: int) -> None:
        if number % 50 == 0 or number == total:
            print(f"companies {number}/{total}", flush=True)

    as_of = datetime.fromisoformat(f"{args.as_of}T23:59:59+00:00")
    store = MacroStore.open(Path(settings.data_dir) / "macro" / "macro.sqlite")
    growth = store.as_of(GDP_SERIES, as_of)
    index = export(
        read_manifest(Path(args.universe)),
        Warehouse.open(Path(args.db)),
        load(Path(args.dataset)),
        LiveForecast.model_validate_json(Path(args.forecast).read_bytes()),
        as_of,
        tuple(date.fromisoformat(origin) for origin in args.origin),
        Path(args.out),
        Path(settings.data_dir) / "cases",
        {day.year: float(item.value) for day, item in growth.items() if item.value is not None},
        show,
    )
    cases = sum(row.has_case for row in index.companies)
    forecasts = sum(row.has_forecast for row in index.companies)
    print(f"{len(index.companies)} companies, {forecasts} forecasts, {cases} cases -> {args.out}")
    return 0


def studio_file(args: argparse.Namespace) -> int:
    case = SimulationCase.model_validate_json(Path(args.case).read_bytes())
    report = build_studio(
        case,
        load_decision(Path(args.decision)),
        StudioInputs.model_validate_json(Path(args.inputs).read_bytes()),
        SimulationReport.model_validate_json(Path(args.report).read_bytes()),
        code_version=code_version(),
    )
    write(Path(args.out), report.model_dump_json(indent=2))
    print(f"{report.manifest.valuation_id} -> {args.out}")
    return 0


def run_case(
    case: SimulationCase,
    decision: DecisionModel,
    settings: SimulationSettings,
    sensitivity: bool = False,
) -> SimulationReport:
    """A run with no clock in what it returns that a report reads (Stage 25 replay)."""
    frame, _ = simulate(case, decision, settings)
    rows: tuple[SensitivityRow, ...] = ()
    if sensitivity:
        rows = tuple(_sensitivity_row(item, case, decision, settings) for item in VARIANTS)
    return build_report(
        case,
        decision,
        settings,
        frame,
        code_version="replay",
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
        seconds=0.0,
        sensitivity=rows,
    )


def report_file(args: argparse.Namespace) -> int:
    from multiverse_simulation.reportdoc import write_report_files

    case = SimulationCase.model_validate_json(Path(args.case).read_bytes())
    report = SimulationReport.model_validate_json(Path(args.report).read_bytes())
    manifest = write_report_files(Path(args.out), report, case, load_decision(Path(args.decision)))
    print(f"{manifest.report_doc_id} -> {args.out}")
    return 0


def replay_file(args: argparse.Namespace) -> int:
    from multiverse_contracts.reports import ReportManifest
    from multiverse_simulation.reportdoc import replay

    path = Path(args.manifest)
    manifest = ReportManifest.model_validate_json(path.read_bytes())
    case = SimulationCase.model_validate_json(Path(args.case).read_bytes())
    check = replay(manifest, path.parent, case, run_case)
    for name, same in check.artifacts:
        print(f"{name}: {'identical' if same else 'DIFFERENT'}")
    print(f"{check.report_doc_id}: {'identical' if check.identical else 'not identical'}")
    return 0 if check.identical else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="multiverse_simulation")
    commands = parser.add_subparsers(dest="command", required=True)
    real = commands.add_parser("companies", help="files of the screens and cases of the worker")
    real.add_argument("--universe", required=True)
    real.add_argument("--db", required=True)
    real.add_argument("--dataset", required=True)
    real.add_argument("--forecast", required=True)
    real.add_argument("--as-of", required=True, dest="as_of")
    real.add_argument("--origin", action="append", required=True, help="repeatable, newest first")
    real.add_argument("--out", default="data/companies")
    run = commands.add_parser("run", help="run a case and write its report")
    run.add_argument("--case", required=True)
    run.add_argument("--decision", required=True)
    run.add_argument("--paths", type=int, default=1000)
    run.add_argument("--seed", type=int, default=20261106)
    run.add_argument("--batch", type=int, default=250)
    run.add_argument("--sensitivity", action="store_true")
    run.add_argument("--out", required=True)
    studio = commands.add_parser("studio", help="build the valuation report of a run")
    studio.add_argument("--case", required=True)
    studio.add_argument("--decision", required=True)
    studio.add_argument("--inputs", required=True)
    studio.add_argument("--report", required=True)
    studio.add_argument("--out", required=True)
    paper = commands.add_parser("report", help="the research report of a run (Stage 25)")
    paper.add_argument("--case", required=True)
    paper.add_argument("--decision", required=True)
    paper.add_argument("--report", required=True)
    paper.add_argument("--out", required=True, help="a folder")
    again = commands.add_parser("replay", help="build a report again from its manifest")
    again.add_argument("--manifest", required=True)
    again.add_argument("--case", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    commands = {
        "companies": companies_file,
        "run": run_file,
        "studio": studio_file,
        "report": report_file,
        "replay": replay_file,
    }
    return commands[args.command](args)
