"""Build a case and run it from the command line.

python -m multiverse_simulation case --cik 0000048898 --origin 2025-12-31 --out <file>
python -m multiverse_simulation run --case <file> --decision <file> --paths 10000 --out <file>
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
from multiverse_contracts.simulation import SensitivityRow, SimulationCase, SimulationSettings
from multiverse_simulation.run import ALTERNATE, METRICS, RISKS, Answer, Frame, simulate
from multiverse_simulation.summary import build_report, ev_change, money

DATASET = "fds-20261028-d9e4acd03365"
BANDS = "evaluation/stage_17_evaluation/bands/gru_attention_q7.npz"
MODEL_ID = "model-20261028-9ce4d4180aa9"
UNIVERSE = "data/universe/sec-1000-20261030.json"
SENSITIVITY_PATHS = 1000
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
            ["git", "describe", "--always", "--dirty"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unversioned"
    return found.stdout.strip() or "unversioned"


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
    Path(args.out).write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"{report.manifest.report_id}: {settings.paths} paths in {seconds:.1f} s -> {args.out}")
    return 0


def case_file(args: argparse.Namespace) -> int:
    # Heavy imports stay here: a run needs neither the warehouse nor scikit-learn.
    from multiverse_forecast.data import load
    from multiverse_pipelines.pit.warehouse import Warehouse
    from multiverse_simulation.casebuild import build_case

    settings = load_settings()
    data = Path(settings.data_dir)
    names = {
        company["cik"]: company["name"]
        for company in json.loads(Path(UNIVERSE).read_text(encoding="utf-8"))["companies"]
    }
    forecast = data / "forecast"
    case = build_case(
        Warehouse.open(data / "pit" / "warehouse.sqlite"),
        load(forecast / DATASET),
        forecast / BANDS,
        args.cik,
        names[args.cik],
        date.fromisoformat(args.origin),
        MODEL_ID,
    )
    Path(args.out).write_text(case.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"{case.case_id}: {len(case.shocks.rows)} quarters of shocks -> {args.out}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="multiverse_simulation")
    commands = parser.add_subparsers(dest="command", required=True)
    case = commands.add_parser("case", help="build a case from local data")
    case.add_argument("--cik", required=True)
    case.add_argument("--origin", required=True)
    case.add_argument("--out", required=True)
    run = commands.add_parser("run", help="run a case and write its report")
    run.add_argument("--case", required=True)
    run.add_argument("--decision", required=True)
    run.add_argument("--paths", type=int, default=1000)
    run.add_argument("--seed", type=int, default=20261106)
    run.add_argument("--batch", type=int, default=250)
    run.add_argument("--sensitivity", action="store_true")
    run.add_argument("--out", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return case_file(args) if args.command == "case" else run_file(args)
