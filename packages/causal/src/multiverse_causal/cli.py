"""Runs the feasibility study.

    python -m multiverse_causal study --dataset var/data/forecast/<dataset id>
        --index var/data/events/decisions.csv --audit var/data/events/quality.json

The study reads no outcome after a treatment and writes ``data/causal/study.json``.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from multiverse_causal.panel import load_panel
from multiverse_causal.study import read_index, run_study
from multiverse_contracts.events import CandidateSample, EventRegistry, QualityAudit
from multiverse_contracts.forecasting import ForecastDatasetManifest

SAMPLE = Path("data/events/sample.json")
REGISTRY = Path("data/events/registry.json")
OUT = Path("data/causal/study.json")
SEED = 20261106


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m multiverse_causal")
    commands = parser.add_subparsers(dest="command", required=True)
    study = commands.add_parser("study", help="the feasibility study, without any effect")
    study.add_argument("--dataset", type=Path, required=True, help="a forecasting dataset folder")
    study.add_argument("--index", type=Path, required=True, help="decision items of the index")
    study.add_argument("--audit", type=Path, required=True, help="the quality audit of Stage 19")
    study.add_argument("--seed", type=int, default=SEED)
    study.add_argument("--out", type=Path, default=OUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = ForecastDatasetManifest.model_validate_json(
            (args.dataset / "manifest.json").read_bytes()
        )
        registry = EventRegistry.model_validate_json(REGISTRY.read_bytes())
        sample = CandidateSample.model_validate_json(SAMPLE.read_bytes())
        audit = QualityAudit.model_validate_json(args.audit.read_bytes())
        panel = load_panel(args.dataset / "dataset.csv")
        study = run_study(
            registry,
            sample,
            audit,
            panel,
            read_index(args.index),
            manifest.dataset_id,
            manifest.data_cutoff,
            args.seed,
            date.today(),
        )
    except (OSError, ValueError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(study.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for line in study.findings:
        print(line)
    print(f"wrote {args.out}: {study.study_id}")
    return 0
