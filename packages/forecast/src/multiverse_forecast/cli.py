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

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    EvaluationProtocol,
    ForecastProtocol,
    SequenceManifest,
)
from multiverse_forecast import evaluation_report
from multiverse_forecast.bands import load_stored, run_baselines
from multiverse_forecast.benchmark import Runner, run
from multiverse_forecast.data import Dataset, load, load_sequences
from multiverse_forecast.report import write_report

PROTOCOL = Path("data/protocols/stage-15-baselines.json")
LARGE = Path("data/protocols/stage-16-temporal-large.json")
EVALUATION = Path("data/protocols/stage-17-evaluation.json")
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
    judge = commands.add_parser("evaluate", help="the quantile forecasts of Stage 17")
    judge.add_argument("step", choices=("train", "baselines", "report"))
    judge.add_argument("--dataset", type=Path, required=True, help="a dataset folder")
    judge.add_argument("--protocol", type=Path, default=EVALUATION)
    judge.add_argument("--base-protocol", type=Path, default=LARGE)
    judge.add_argument("--benchmark", type=Path, required=True, help="the Stage 16 report.json")
    judge.add_argument("--baselines", type=Path, required=True, help="the Stage 15 report.json")
    judge.add_argument("--device", default="auto", help="auto, cpu or cuda")
    judge.add_argument("--out", type=Path, default=OUT)
    judge.add_argument("--figures", type=Path, help="also write the plots here")
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


def _evaluate(args: argparse.Namespace) -> int:
    raw = args.protocol.read_bytes()
    protocol = EvaluationProtocol.model_validate_json(raw)
    base_raw = args.base_protocol.read_bytes()
    base = ForecastProtocol.model_validate_json(base_raw)
    if hashlib.sha256(base_raw).hexdigest() != protocol.base_protocol_sha256:
        raise ValueError("the protocol was written for another base protocol")
    benchmark = BenchmarkReport.model_validate_json(args.benchmark.read_bytes())
    if benchmark.benchmark_id != protocol.benchmark_id:
        raise ValueError("the protocol names another Stage 16 benchmark")
    baselines = BenchmarkReport.model_validate_json(args.baselines.read_bytes())
    dataset = load(args.dataset)
    if baselines.dataset_sha256 != dataset.manifest.sha256:
        raise ValueError("the Stage 15 report was built on another dataset")
    root = args.out / "evaluation" / protocol.protocol_id

    def show(line: str) -> None:
        print(line, file=sys.stderr, flush=True)

    if args.step == "train":
        # PyTorch is an optional extra: imported only for this step.
        from multiverse_forecast.evaluation import run_trainings
        from multiverse_forecast.neural import Config

        sequences, sequences_id = load_sequences(args.dataset, dataset)
        run_trainings(
            dataset,
            sequences,
            sequences_id,
            base,
            protocol,
            benchmark,
            Config(device=args.device),
            root,
            show,
        )
    elif args.step == "baselines":
        runner = Runner(dataset, base)
        run_baselines(runner, baselines, protocol, base.test_years, root / "bands", show)
    else:
        stored = load_stored(root / "bands")
        manifest = SequenceManifest.model_validate_json(
            (args.dataset / "sequences.json").read_bytes()
        )
        measured = evaluation_report.measure(dataset, base, protocol, stored)
        package = evaluation_report.build(
            dataset,
            manifest.sequences_id,
            protocol,
            hashlib.sha256(raw).hexdigest(),
            benchmark,
            measured,
            stored,
        )
        folder = evaluation_report.write(package, protocol, args.out, args.figures)
        for line in (*package.findings, *package.failures):
            print(line)
        print(f"{package.evaluation_id}: model {package.model_id}")
        print(f"wrote {folder}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "evaluate":
            return _evaluate(args)
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
