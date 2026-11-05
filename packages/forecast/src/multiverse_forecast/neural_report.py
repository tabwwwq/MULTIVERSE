"""The Stage 16 benchmark report: the temporal model against Stage 15, row for row.

Both benchmarks score the same rows (same dataset, folds, cold-start firms, scoreable
rule), so every comparison checks that the example counts agree before it compares. The
report names the dataset, both protocols and every training run; its findings say, per
population, target and horizon, whether the network beats persistence and the best
Stage 15 model, by MAE and by median AE, and how much the seeds disagree.
"""

import html
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    ForecastProtocol,
    Population,
    ScoreRow,
    SplitName,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_forecast.data import Dataset, canonical_sha256
from multiverse_forecast.neural_run import NeuralBenchmark
from multiverse_forecast.report import CSS, TITLES

BASELINES = ("seasonal_naive", "sector_average", "panel_ar", "ridge", "elastic_net", "gbm")


def _find(
    scores: tuple[ScoreRow, ...] | list[ScoreRow],
    target: object,
    horizon: int,
    split: SplitName,
    population: Population,
    model: str,
) -> ScoreRow | None:
    return next(
        (
            s
            for s in scores
            if s.target is target
            and s.horizon == horizon
            and s.split is split
            and s.population is population
            and s.model == model
        ),
        None,
    )


def compare(
    neural: list[ScoreRow], baselines: BenchmarkReport, protocol: ForecastProtocol
) -> tuple[list[str], list[list[str]]]:
    """Findings and table rows: the network against persistence and the best baseline."""
    findings: list[str] = []
    rows: list[list[str]] = []
    for model, split, population, target, horizon in itertools.product(
        protocol.grids,
        (SplitName.TEST, SplitName.COLD_START),
        Population,
        protocol.targets,
        protocol.horizons,
    ):
        mine = _find(neural, target, horizon, split, population, model)
        naive = _find(baselines.scores, target, horizon, split, population, "persistence")
        if mine is None or naive is None:
            continue
        if mine.examples != naive.examples:
            raise ValueError(
                f"{target.value} h={horizon} {split.value} {population.value}: "
                f"{mine.examples} rows here, {naive.examples} in Stage 15"
            )
        others = [
            s
            for m in BASELINES
            if (s := _find(baselines.scores, target, horizon, split, population, m)) is not None
        ]
        best = min(others, key=lambda s: s.mae)
        seeds = [
            s.mae
            for r in range(1, protocol.repeats + 1)
            if (s := _find(neural, target, horizon, split, population, f"{model}_seed{r}"))
        ]
        change = 100 * (mine.vs_naive or 0)
        interval = f"{100 * (mine.vs_naive_low or 0):+.1f}..{100 * (mine.vs_naive_high or 0):+.1f}%"
        versus_best = 100 * (mine.mae / best.mae - 1)
        rows.append(
            [
                model,
                split.value,
                population.value,
                target.value,
                str(horizon),
                str(mine.examples),
                f"{naive.mae:.4g}",
                f"{best.model} {best.mae:.4g}",
                f"{mine.mae:.4g} ({change:+.1f}%, {interval})",
                f"{versus_best:+.1f}%",
                f"{min(seeds):.4g}..{max(seeds):.4g}" if seeds else "-",
                f"{naive.median_ae:.3g} / {best.median_ae:.3g} / {mine.median_ae:.3g}",
            ]
        )
        if split is SplitName.TEST:
            beats_naive = mine.vs_naive_high is not None and mine.vs_naive_high < 0
            findings.append(
                f"{model} {target.value} h={horizon} ({population.value}): MAE {mine.mae:.4g}, "
                f"{change:+.1f}% vs persistence ({interval}"
                f"{', below zero' if beats_naive else ', includes zero or above'}); "
                f"{versus_best:+.1f}% vs best baseline {best.model}; median AE persistence "
                f"{naive.median_ae:.3g}, {best.model} {best.median_ae:.3g}, network "
                f"{mine.median_ae:.3g}"
            )
    return findings, rows


def choice_findings(result: NeuralBenchmark, protocol: ForecastProtocol) -> list[str]:
    """One finding per setting and per choice: a finding is short, a grid is not."""
    scored = [
        f"validation score {score:.4f} (mean over targets of MAE over persistence MAE, lower "
        f"is better) of {setting}"
        for setting, score in result.choice.items()
    ]
    chosen = [
        f"chosen on validation: {c.model} " + ", ".join(f"{p.name}={p.value}" for p in c.params)
        for c in result.configs
        if c.target is protocol.targets[0]
    ]
    return scored + chosen


def report(
    dataset: Dataset,
    protocol: ForecastProtocol,
    protocol_sha256: str,
    result: NeuralBenchmark,
    baselines: BenchmarkReport,
) -> tuple[BenchmarkReport, list[list[str]]]:
    findings, rows = compare(result.scores, baselines, protocol)
    findings = choice_findings(result, protocol) + findings
    payload = {
        "dataset": dataset.manifest.sha256,
        "protocol": protocol_sha256,
        "baselines": baselines.sha256,
        "configs": [c.model_dump(mode="json") for c in result.configs],
        "scores": [s.model_dump(mode="json") for s in result.scores],
        "runs": [r.checkpoint_sha256 for r in result.runs],
    }
    digest = canonical_sha256(payload)
    built = BenchmarkReport(
        benchmark_id=f"bench-{dataset.manifest.dataset_id.split('-')[1]}-{digest[:12]}",
        sha256=digest,
        dataset_id=dataset.manifest.dataset_id,
        dataset_sha256=dataset.manifest.sha256,
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol_sha256,
        seed=protocol.seed,
        configs=tuple(result.configs),
        scores=tuple(result.scores),
        findings=tuple(findings),
        failures=tuple(f"training run {r.run_id}" for r in result.runs if r.best_epoch == 1),
        contracts_version=CONTRACTS_VERSION,
        created_at=datetime.now(UTC),
    )
    return built, rows


HEAD = (
    "Model",
    "Split",
    "Population",
    "Target",
    "h",
    "Rows",
    "Persistence MAE",
    "Best baseline MAE",
    "Network MAE (vs persistence, 95%)",
    "Network vs best",
    "Seed MAE range",
    "Median AE: persistence / best / network",
)


def models(built: BenchmarkReport) -> list[str]:
    return sorted({c.model for c in built.configs})


def markdown(built: BenchmarkReport, rows: list[list[str]], baselines: BenchmarkReport) -> str:
    lines = [
        f"# Stage 16 benchmark `{built.benchmark_id}`",
        "",
        f"Temporal models ({', '.join(models(built))}) against the Stage 15 baselines "
        f"`{baselines.benchmark_id}` on "
        f"the same rows. Dataset `{built.dataset_id}`, protocol `{built.protocol_id}` "
        f"(SHA-256 `{built.protocol_sha256}`).",
        "",
        "## Findings",
        "",
        *(f"- {f}" for f in built.findings),
        "",
        "## Comparison",
        "",
        "| " + " | ".join(HEAD) + " |",
        "|---" * len(HEAD) + "|",
        *("| " + " | ".join(r) + " |" for r in rows),
        "",
    ]
    return "\n".join(lines)


def page(built: BenchmarkReport, rows: list[list[str]]) -> str:
    th = "".join(f"<th>{html.escape(h)}</th>" for h in HEAD)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in rows
    )
    titles = " · ".join(TITLES.values())
    viewport = '<meta name="viewport" content="width=device-width,initial-scale=1">'
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">{viewport}\n'
        f"<title>Temporal model benchmark</title><style>{CSS}</style></head>\n<body><main>\n"
        "<h1>Stage 16: temporal model against the baselines</h1>"
        f"<p class='lede'>Benchmark <code>{html.escape(built.benchmark_id)}</code> · dataset "
        f"<code>{html.escape(built.dataset_id)}</code> · protocol "
        f"<code>{html.escape(built.protocol_id)}</code>. Targets: {html.escape(titles)}.</p>"
        "<h2>Findings</h2><ul>"
        + "".join(f"<li>{html.escape(f)}</li>" for f in built.findings)
        + "</ul><h2>Comparison on the same rows</h2>"
        f"<div class='box'><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody>"
        "</table></div>\n</main></body></html>\n"
    )


def write(
    built: BenchmarkReport, rows: list[list[str]], baselines: BenchmarkReport, root: Path
) -> Path:
    folder = root / built.benchmark_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_bytes(
        (json.dumps(built.model_dump(mode="json"), indent=2) + "\n").encode("utf-8")
    )
    (folder / "report.md").write_bytes(markdown(built, rows, baselines).encode("utf-8"))
    (folder / "report.html").write_bytes(page(built, rows).encode("utf-8"))
    return folder
