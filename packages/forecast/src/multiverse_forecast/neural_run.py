"""Trainings of the temporal model under the Stage 15 protocol (Stage 16).

A fold year Y follows Stage 15 exactly: the cold-start firms never train; a label trains
only if it was released before Y began; the model then forecasts the origins of Y, scored
on the rows and with the measures of Stage 15, against persistence on the same rows.
Early stopping watches a seeded tenth of the training firms, whose labels obey the same
release rule.

- ``run_fold``: one training, scored on its fold (the smoke run caps rows and epochs: it
  shows that the machinery works, not how good the model is);
- ``benchmark``: per model of the protocol's grids (``gru_attention``, ``tcn``), the
  setting chosen on the validation years, then ``repeats`` trainings per test year with
  seeds seed, seed + 1, ...; each seed is scored, and so is the mean of their forecasts.

Each training writes ``var/data/forecast/neural/<run id>/`` (never committed):
``checkpoint.pt``, ``run.json`` (``TrainingRun``), ``log.jsonl``, ``plot.svg`` (the
curves of that run) and, for ``run_fold``, ``scores.json``.
"""

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch

from multiverse_contracts.forecasting import (
    EpochLog,
    ForecastProtocol,
    ModelConfig,
    Param,
    ScoreRow,
    SplitName,
    TrainingRun,
)
from multiverse_forecast.benchmark import Prediction, Runner, boundary, watch_rows
from multiverse_forecast.data import Dataset, Floats, canonical_sha256
from multiverse_forecast.models import Prep, persistence_values
from multiverse_forecast.neural import (
    HORIZONS,
    TARGETS,
    Arrays,
    Config,
    SequencePrep,
    Trained,
    channel_transform,
    device_for,
    load_checkpoint,
    predict,
    save_checkpoint,
    train,
)
from multiverse_forecast.probabilistic import to_target_space

MODEL = "gru_attention"
VALIDATION_HORIZONS = (1, 4, 8)
Pair = tuple[int, int]


@dataclass(frozen=True)
class RunResult:
    run: TrainingRun
    scores: list[ScoreRow]
    folder: Path


@dataclass(frozen=True)
class Fold:
    year: int
    data: Arrays
    train_rows: np.ndarray
    valid_rows: np.ndarray


def labels_until(dataset: Dataset, released_before: np.datetime64 | None) -> Floats:
    """Targets in training space [rows, targets, horizons]; NaN unless usable."""
    out = np.full((dataset.x.shape[0], len(TARGETS), len(HORIZONS)), np.nan)
    for t, target in enumerate(TARGETS):
        for h, horizon in enumerate(HORIZONS):
            found = dataset.targets.get((target, horizon))
            if found is None:
                continue
            usable = ~np.isnan(found.value)
            if released_before is not None:
                usable &= found.released <= released_before
            out[usable, t, h] = to_target_space(target, found.value[usable])
    return out


def fold(
    runner: Runner,
    sequences: Floats,
    year: int,
    seed: int,
    max_train_rows: int | None = None,
) -> Fold:
    """Rows and arrays of fold Y, every transform fitted on its training rows only."""
    dataset, protocol = runner.ds, runner.protocol
    labels = labels_until(dataset, boundary(year))
    has_label = ~np.isnan(labels).all(axis=(1, 2))
    watched = watch_rows(runner)
    candidates = ~runner.cold & has_label & (dataset.years < year)
    train_rows = np.flatnonzero(candidates & ~watched)
    valid_rows = np.flatnonzero(candidates & watched)
    if max_train_rows is not None and train_rows.size > max_train_rows:
        rng = np.random.default_rng(seed)
        train_rows = np.sort(rng.choice(train_rows, size=max_train_rows, replace=False))
        keep = min(valid_rows.size, max_train_rows // 4)
        valid_rows = np.sort(rng.choice(valid_rows, size=keep, replace=False))
    transformed = channel_transform(sequences)
    seq_prep = SequencePrep().fit(transformed[train_rows])
    values, mask = seq_prep.transform(transformed)
    static_prep = Prep(protocol.winsor_quantile).fit(
        dataset.x[train_rows], dataset.features, dataset.divisions[train_rows]
    )
    static = static_prep.transform(dataset.x, dataset.divisions)
    return Fold(year, Arrays(values, mask, static, labels), train_rows, valid_rows)


def svg_plot(epochs: list[EpochLog], title: str) -> str:
    """Training and validation loss of one run, drawn from its log."""
    width, height, pad = 640, 320, 48
    values = [e.train_loss for e in epochs] + [e.validation_loss for e in epochs]
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    count = max(len(epochs) - 1, 1)

    def point(i: int, v: float) -> str:
        x = pad + (width - 2 * pad) * i / count
        y = height - pad - (height - 2 * pad) * (v - low) / span
        return f"{x:.1f},{y:.1f}"

    train_line = " ".join(point(i, e.train_loss) for i, e in enumerate(epochs))
    valid_line = " ".join(point(i, e.validation_loss) for i, e in enumerate(epochs))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="system-ui,sans-serif" font-size="12">'
        f'<rect width="100%" height="100%" fill="#fff"/>'
        f'<text x="{pad}" y="24" font-size="14">{title}</text>'
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" '
        f'stroke="#999"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#999"/>'
        f'<text x="{pad}" y="{height - 16}">epoch 1</text>'
        f'<text x="{width - pad - 50}" y="{height - 16}">epoch {len(epochs)}</text>'
        f'<text x="4" y="{pad + 4}">{high:.3f}</text>'
        f'<text x="4" y="{height - pad}">{low:.3f}</text>'
        f'<polyline fill="none" stroke="#2f5d8a" stroke-width="2" points="{train_line}"/>'
        f'<polyline fill="none" stroke="#a33b3b" stroke-width="2" stroke-dasharray="6 4" '
        f'points="{valid_line}"/>'
        f'<text x="{width - 220}" y="{pad}" fill="#2f5d8a">training loss</text>'
        f'<text x="{width - 220}" y="{pad + 16}" fill="#a33b3b">'
        "validation loss (early stopping)</text>"
        "</svg>\n"
    )


def save_run(
    runner: Runner,
    sequences_id: str,
    current: Fold,
    trained: Trained,
    config: Config,
    out: Path,
    *,
    smoke: bool,
    max_train_rows: int | None,
    evaluated: int,
    model: str = MODEL,
) -> tuple[TrainingRun, Path]:
    """Checkpoint, manifest, log and plot of one training; the checkpoint round trip must
    give the same forecasts."""
    dataset = runner.ds
    pending = out / "pending"
    shutil.rmtree(pending, ignore_errors=True)
    pending.mkdir(parents=True)
    checkpoint = pending / "checkpoint.pt"
    save_checkpoint(checkpoint, trained.model, config, {}, trained.best_epoch)
    reloaded, _, _ = load_checkpoint(checkpoint)
    reloaded.to(device_for(config))
    probe = current.valid_rows[:256]
    same = np.allclose(
        predict(trained.model, current.data, probe, config),
        predict(reloaded, current.data, probe, config),
        rtol=0,
        atol=1e-6,
    )
    if not same:
        raise RuntimeError("the reloaded checkpoint forecasts differently")
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    params = (
        *(Param(name=k, value=v) for k, v in sorted(config.params().items())),
        Param(name="max_train_rows", value=str(max_train_rows or "all")),
    )
    identity = canonical_sha256(
        {
            "dataset": dataset.manifest.sha256,
            "sequences": sequences_id,
            "fold": current.year,
            "params": [p.model_dump() for p in params],
            "checkpoint": digest,
        }
    )
    run = TrainingRun(
        run_id=f"run-{dataset.manifest.dataset_id.split('-')[1]}-{identity[:12]}",
        model=model,
        purpose="smoke" if smoke else "benchmark",
        dataset_id=dataset.manifest.dataset_id,
        sequences_id=sequences_id,
        fold_year=current.year,
        seed=config.seed,
        device=str(device_for(config)),
        torch_version=torch.__version__,
        params=params,
        train_rows=int(current.train_rows.size),
        validation_rows=int(current.valid_rows.size),
        evaluated_rows=evaluated,
        epochs=tuple(trained.epochs),
        best_epoch=trained.best_epoch,
        checkpoint_sha256=digest,
        created_at=datetime.now(UTC),
    )
    folder = out / run.run_id
    shutil.rmtree(folder, ignore_errors=True)
    pending.rename(folder)
    (folder / "run.json").write_bytes((run.model_dump_json(indent=2) + "\n").encode("utf-8"))
    (folder / "log.jsonl").write_bytes(
        "".join(e.model_dump_json() + "\n" for e in trained.epochs).encode("utf-8")
    )
    title = f"{model}, fold {current.year}, seed {config.seed}{' (smoke)' if smoke else ''}"
    (folder / "plot.svg").write_bytes(svg_plot(trained.epochs, title).encode("utf-8"))
    return run, folder


def eval_rows(
    runner: Runner, year: int, eligible: np.ndarray | None = None
) -> dict[Pair, np.ndarray]:
    """Per (target, horizon) index: the scoreable rows of one year (the Stage 15 rows)."""
    found = {}
    for t, target in enumerate(TARGETS):
        if target not in runner.protocol.targets:
            continue
        for h, horizon in enumerate(HORIZONS):
            if horizon not in runner.protocol.horizons:
                continue
            mask = (runner.ds.years == year) & runner.scoreable(target, horizon)
            if eligible is not None:
                mask &= eligible
            rows = np.flatnonzero(mask)
            if rows.size:
                found[(t, h)] = rows
    return found


def split_scores(
    runner: Runner, model: str, pair: Pair, rows: np.ndarray, point: Floats
) -> list[ScoreRow]:
    t, h = pair
    scores: list[ScoreRow] = []
    cold = runner.cold[rows]
    for split, part in ((SplitName.TEST, ~cold), (SplitName.COLD_START, cold)):
        if part.any():
            scores += runner.scores(
                TARGETS[t], HORIZONS[h], split, model, Prediction(rows[part], point[part])
            )
    return scores


def run_fold(
    dataset: Dataset,
    sequences: Floats,
    sequences_id: str,
    protocol: ForecastProtocol,
    fold_year: int,
    config: Config,
    out: Path,
    *,
    smoke: bool = False,
    max_train_rows: int | None = None,
) -> RunResult:
    runner = Runner(dataset, protocol)
    current = fold(runner, sequences, fold_year, config.seed, max_train_rows)
    trained = train(current.data, current.train_rows, current.valid_rows, config)
    scores: list[ScoreRow] = []
    by_pair = eval_rows(runner, fold_year)
    for pair, rows in by_pair.items():
        point = predict(trained.model, current.data, rows, config)[:, pair[0], pair[1], 1]
        scores += split_scores(runner, MODEL, pair, rows, point)
    run, folder = save_run(
        runner,
        sequences_id,
        current,
        trained,
        config,
        out,
        smoke=smoke,
        max_train_rows=max_train_rows,
        evaluated=len({int(r) for rows in by_pair.values() for r in rows}),
    )
    (folder / "scores.json").write_bytes(
        (json.dumps([s.model_dump(mode="json") for s in scores], indent=2) + "\n").encode("utf-8")
    )
    return RunResult(run, scores, folder)


@dataclass(frozen=True)
class NeuralBenchmark:
    configs: list[ModelConfig]
    scores: list[ScoreRow]
    runs: list[TrainingRun]
    choice: dict[str, float]
    """Validation score of each setting: mean over targets of MAE over persistence MAE."""


def setting(base: Config, model: str, params: tuple[Param, ...], seed: int) -> Config:
    values = {p.name: p.value for p in params}
    return replace(
        base,
        arch="tcn" if model == "tcn" else "gru_attention",
        hidden=int(values.get("hidden", base.hidden)),
        layers=int(values.get("layers", base.layers)),
        dropout=float(values.get("dropout", base.dropout)),
        learning_rate=float(values.get("learning_rate", base.learning_rate)),
        max_epochs=int(values.get("max_epochs", base.max_epochs)),
        patience=int(values.get("patience", base.patience)),
        seed=seed,
    )


def _abs_errors(
    runner: Runner, pair: Pair, rows: np.ndarray, point: Floats
) -> tuple[Floats, Floats]:
    target = TARGETS[pair[0]]
    actual = runner.ds.targets[(target, HORIZONS[pair[1]])].value[rows]
    naive = persistence_values(runner.ds.x[rows], runner.ds.features, target)
    return np.abs(point - actual), np.abs(naive - actual)


def benchmark(
    dataset: Dataset,
    sequences: Floats,
    sequences_id: str,
    protocol: ForecastProtocol,
    base: Config,
    out: Path,
    progress: Callable[[str], None] = print,
) -> NeuralBenchmark:
    runner = Runner(dataset, protocol)
    configs: list[ModelConfig] = []
    scores: list[ScoreRow] = []
    runs: list[TrainingRun] = []
    choice: dict[str, float] = {}
    for model, grid in protocol.grids.items():
        found = _benchmark_model(runner, sequences, sequences_id, model, grid, base, out, progress)
        configs += found.configs
        scores += found.scores
        runs += found.runs
        choice |= found.choice
    return NeuralBenchmark(configs, scores, runs, choice)


def _benchmark_model(
    runner: Runner,
    sequences: Floats,
    sequences_id: str,
    model: str,
    grid: tuple[tuple[Param, ...], ...],
    base: Config,
    out: Path,
    progress: Callable[[str], None],
) -> NeuralBenchmark:
    dataset, protocol = runner.ds, runner.protocol
    validation_end = boundary(min(protocol.test_years))
    runs: list[TrainingRun] = []
    choice: dict[str, float] = {}
    best: tuple[float, tuple[Param, ...], dict[Pair, tuple[np.ndarray, Floats]]] | None = None
    for params in grid:
        config = setting(base, model, params, protocol.seed)
        named = ", ".join(f"{p.name}={p.value}" for p in params)
        pooled: dict[Pair, tuple[list[np.ndarray], list[Floats]]] = {}
        for year in protocol.validation_years:
            current = fold(runner, sequences, year, config.seed)
            trained = train(current.data, current.train_rows, current.valid_rows, config)
            for pair, rows in eval_rows(runner, year, ~runner.cold).items():
                target, horizon = TARGETS[pair[0]], HORIZONS[pair[1]]
                if horizon not in VALIDATION_HORIZONS:
                    continue
                rows = rows[dataset.targets[(target, horizon)].released[rows] <= validation_end]
                if rows.size == 0:
                    continue
                point = predict(trained.model, current.data, rows, config)[:, pair[0], pair[1], 1]
                pooled.setdefault(pair, ([], []))
                pooled[pair][0].append(rows)
                pooled[pair][1].append(point)
            run, _ = save_run(
                runner,
                sequences_id,
                current,
                trained,
                config,
                out,
                smoke=False,
                max_train_rows=None,
                evaluated=0,
                model=model,
            )
            runs.append(run)
            progress(
                f"{model} validation {year} ({named}): {len(run.epochs)} epochs, "
                f"best {run.best_epoch}"
            )
        joined = {k: (np.concatenate(v[0]), np.concatenate(v[1])) for k, v in pooled.items()}
        ratios = []
        for t in range(len(TARGETS)):
            pairs = [k for k in joined if k[0] == t]
            if not pairs:
                continue
            errors = [_abs_errors(runner, k, *joined[k]) for k in pairs]
            model_abs = np.concatenate([e[0] for e in errors])
            naive_abs = np.concatenate([e[1] for e in errors])
            ratios.append(float(model_abs.mean() / naive_abs.mean()))
        score = float(np.mean(ratios))
        choice[f"{model}: {named}"] = score
        if best is None or score < best[0]:
            best = (score, params, joined)
    assert best is not None
    _, params, joined = best
    scores: list[ScoreRow] = []
    configs: list[ModelConfig] = []
    for t, target in enumerate(TARGETS):
        pairs = [k for k in joined if k[0] == t]
        if not pairs:
            continue
        model_abs = np.concatenate([_abs_errors(runner, k, *joined[k])[0] for k in pairs])
        configs.append(
            ModelConfig(
                target=target, model=model, params=params, validation_mae=float(model_abs.mean())
            )
        )
        for k in pairs:
            scores += runner.scores(
                target, HORIZONS[k[1]], SplitName.VALIDATION, model, Prediction(*joined[k])
            )
    collected: dict[Pair, tuple[list[np.ndarray], list[list[Floats]]]] = {}
    for year in protocol.test_years:
        by_pair = eval_rows(runner, year)
        per_seed: list[dict[Pair, Floats]] = []
        for repeat in range(protocol.repeats):
            config = setting(base, model, params, protocol.seed + repeat)
            current = fold(runner, sequences, year, config.seed)
            trained = train(current.data, current.train_rows, current.valid_rows, config)
            per_seed.append(
                {
                    k: predict(trained.model, current.data, rows, config)[:, k[0], k[1], 1]
                    for k, rows in by_pair.items()
                }
            )
            run, _ = save_run(
                runner,
                sequences_id,
                current,
                trained,
                config,
                out,
                smoke=False,
                max_train_rows=None,
                evaluated=len({int(r) for rows in by_pair.values() for r in rows}),
                model=model,
            )
            runs.append(run)
            progress(
                f"{model} test {year} seed {config.seed}: {len(run.epochs)} epochs, "
                f"best {run.best_epoch}"
            )
        for k, rows in by_pair.items():
            collected.setdefault(k, ([], [[] for _ in range(protocol.repeats)]))
            collected[k][0].append(rows)
            for repeat in range(protocol.repeats):
                collected[k][1][repeat].append(per_seed[repeat][k])
    for pair, (rows_list, seeds) in collected.items():
        rows = np.concatenate(rows_list)
        points = [np.concatenate(s) for s in seeds]
        scores += split_scores(runner, model, pair, rows, np.mean(points, axis=0))
        for repeat, point in enumerate(points):
            scores += split_scores(runner, f"{model}_seed{repeat + 1}", pair, rows, point)
    return NeuralBenchmark(configs, scores, runs, choice)
