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

from multiverse_contracts.forecasting import BenchmarkReport, ForecastProtocol
from multiverse_forecast.benchmark import run
from multiverse_forecast.data import Dataset, load, load_sequences
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
    neural = commands.add_parser("neural", help="train the temporal model on one fold")
    neural.add_argument("--dataset", type=Path, required=True, help="a dataset folder")
    neural.add_argument("--protocol", type=Path, default=PROTOCOL)
    neural.add_argument("--fold", type=int, required=True, help="the fold year it forecasts")
    neural.add_argument("--smoke", action="store_true", help="a short run of the machinery")
    neural.add_argument("--max-train-rows", type=int)
    neural.add_argument("--epochs", type=int, default=40)
    neural.add_argument("--hidden", type=int, default=64)
    neural.add_argument("--device", default="auto", help="auto, cpu or cuda")
    neural.add_argument("--out", type=Path, default=OUT / "neural")
    full = commands.add_parser("neural-benchmark", help="the temporal model against Stage 15")
    full.add_argument("--dataset", type=Path, required=True, help="a dataset folder")
    full.add_argument(
        "--protocol", type=Path, default=Path("data/protocols/stage-16-temporal.json")
    )
    full.add_argument("--baselines", type=Path, required=True, help="the Stage 15 report.json")
    full.add_argument("--device", default="auto", help="auto, cpu or cuda")
    full.add_argument("--out", type=Path, default=OUT)
    return parser


def _neural_benchmark(
    args: argparse.Namespace, dataset: Dataset, protocol: ForecastProtocol, protocol_sha: str
) -> int:
    from multiverse_forecast import neural_report
    from multiverse_forecast.neural import Config
    from multiverse_forecast.neural_run import benchmark

    baselines = BenchmarkReport.model_validate_json(args.baselines.read_bytes())
    if baselines.dataset_sha256 != dataset.manifest.sha256:
        raise ValueError("the Stage 15 report was built on another dataset")
    sequences, sequences_id = load_sequences(args.dataset, dataset)

    def show(line: str) -> None:
        print(line, file=sys.stderr, flush=True)

    result = benchmark(
        dataset,
        sequences,
        sequences_id,
        protocol,
        Config(device=args.device),
        args.out / "neural",
        show,
    )
    built, rows = neural_report.report(dataset, protocol, protocol_sha, result, baselines)
    folder = neural_report.write(built, rows, baselines, args.out)
    for line in built.findings:
        print(line)
    print(f"{built.benchmark_id}: {len(result.runs)} trainings, {len(built.scores)} scores")
    print(f"wrote {folder}")
    return 0


def _neural(args: argparse.Namespace, dataset: Dataset, protocol: ForecastProtocol) -> int:
    # PyTorch is an optional extra: imported only for this command.
    from multiverse_forecast.neural import Config
    from multiverse_forecast.neural_run import run_fold

    sequences, sequences_id = load_sequences(args.dataset, dataset)
    config = Config(hidden=args.hidden, max_epochs=args.epochs, device=args.device)
    result = run_fold(
        dataset,
        sequences,
        sequences_id,
        protocol,
        args.fold,
        config,
        args.out,
        smoke=args.smoke,
        max_train_rows=args.max_train_rows,
    )
    run = result.run
    last = run.epochs[-1]
    print(
        f"{run.run_id}: {len(run.epochs)} epochs, best {run.best_epoch}, train loss "
        f"{last.train_loss:.4f}, validation loss {last.validation_loss:.4f}, "
        f"{sum(e.seconds for e in run.epochs):.0f} s on {run.device}"
    )
    print(f"wrote {result.folder}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        raw = args.protocol.read_bytes()
        protocol = ForecastProtocol.model_validate_json(raw)
        dataset = load(args.dataset)
        if args.command == "neural":
            return _neural(args, dataset, protocol)
        if args.command == "neural-benchmark":
            return _neural_benchmark(args, dataset, protocol, hashlib.sha256(raw).hexdigest())
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
