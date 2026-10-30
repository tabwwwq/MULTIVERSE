"""Forecasting baselines: ``python -m multiverse_forecast benchmark``.

Reads a dataset folder written by ``multiverse_pipelines.forecastset`` and the locked
protocol in ``data/protocols/``; writes the benchmark report into
``var/data/forecast/<benchmark id>/`` (never committed). No network, no new data.
"""

import argparse
import hashlib
import sys
from collections.abc import Sequence
from pathlib import Path

from multiverse_contracts.forecasting import ForecastProtocol
from multiverse_forecast.benchmark import run
from multiverse_forecast.data import load
from multiverse_forecast.report import write_report

PROTOCOL = Path("data/protocols/stage-15-baselines.json")
OUT = Path("var/data/forecast")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m multiverse_forecast", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    bench = commands.add_parser("benchmark", help="every baseline under the locked protocol")
    bench.add_argument("--dataset", type=Path, required=True, help="a dataset folder")
    bench.add_argument("--protocol", type=Path, default=PROTOCOL)
    bench.add_argument("--out", type=Path, default=OUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        raw = args.protocol.read_bytes()
        protocol = ForecastProtocol.model_validate_json(raw)
        dataset = load(args.dataset)
    except (OSError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    report = run(dataset, protocol, hashlib.sha256(raw).hexdigest())
    folder = write_report(report, args.out)
    for line in report.findings:
        print(line)
    print(f"{report.benchmark_id}: {len(report.scores)} scores")
    print(f"wrote {folder}")
    return 0
