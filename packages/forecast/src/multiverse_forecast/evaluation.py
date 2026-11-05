"""Stage 17 trainings: the temporal model with seven quantiles, fold by fold, and ablations.

Stage 16 chose the settings on validation; here they are fixed. Each test year is a fold
of Stage 16 (same firms, same release rule), trained ``repeats`` times; the mean of the
seeds' quantiles is the forecast. The watch firms, which only stop the training, calibrate
it: their labels were all released before the fold year, so nothing of the year leaks.

An ablation removes one input from the same trainings and keeps the rows that are scored:

- ``no_macro``, ``no_rnd``, ``no_debt``: those features and channels become missing;
- ``lags_12``, ``lags_4``: the sequence stops that many quarters back (the static features
  keep their lags 1 to 8);
- ``no_sequence``, ``no_static``: one of the two input branches is gone;
- ``no_masks``: the model is told that everything was observed;
- ``other_depth``: one layer instead of two, or two instead of one.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    EvaluationProtocol,
    ForecastProtocol,
    Param,
    TrainingRun,
)
from multiverse_forecast.bands import (
    CONDITIONS,
    HORIZONS,
    NETWORKS,
    TARGETS,
    Bands,
    load_stored,
    save_arrays,
    year_rows,
)
from multiverse_forecast.benchmark import Runner
from multiverse_forecast.data import Dataset, Floats
from multiverse_forecast.evaluation_scores import choose_primary, entries_of, scope_of
from multiverse_forecast.neural import Arrays, Config, predict, train
from multiverse_forecast.neural_run import Fold, fold, save_run, setting
from multiverse_forecast.probabilistic import conformal_offset, pinball_rows

RND_CHANNEL = 6
DEBT_CHANNEL = 8
RECENT_QUARTERS = 4
Tweak = Callable[[Fold], Fold]


@dataclass(frozen=True)
class Variant:
    name: str
    model: str
    params: tuple[Param, ...]
    repeats: int
    dataset: Dataset
    sequences: Floats
    tweak: Tweak | None = None


@dataclass
class Trainings:
    bands: Bands
    runs: list[TrainingRun]
    partial: Bands | None
    """The mean of the first ``ablation_repeats`` seeds, the fair partner of an ablation."""
    medians: np.ndarray
    """Median forecast of each seed: [seeds, rows, targets, horizons]."""
    memory: Floats
    """Pinball sums and counts, first seed: [years, trained / watched, targets, horizons, 2]."""


def without_features(dataset: Dataset, *parts: str) -> Dataset:
    x = dataset.x.copy()
    x[:, [i for i, f in enumerate(dataset.features) if any(p in f for p in parts)]] = np.nan
    return replace(dataset, x=x)


def without_channel(sequences: Floats, channel: int) -> Floats:
    out = sequences.copy()
    out[:, :, channel] = np.nan
    return out


def shorter(sequences: Floats, quarters: int) -> Floats:
    out = sequences.copy()
    out[:, :-quarters] = np.nan
    return out


def _all_observed(current: Fold) -> Fold:
    data = current.data
    return replace(current, data=replace(data, mask=np.ones_like(data.mask)))


def _no_static(current: Fold) -> Fold:
    data = current.data
    return replace(current, data=replace(data, static=np.zeros_like(data.static)))


def ablation(name: str, full: Variant, repeats: int) -> Variant:
    """The full model without one input; the rows it is scored on stay the same."""
    data, sequences = full.dataset, full.sequences
    base = replace(full, name=f"ablation_{name}", repeats=repeats)
    if name == "no_macro":
        return replace(base, dataset=without_features(data, "macro_"))
    if name == "no_rnd":
        return replace(
            base,
            dataset=without_features(data, "rnd"),
            sequences=without_channel(sequences, RND_CHANNEL),
        )
    if name == "no_debt":
        return replace(
            base,
            dataset=without_features(data, "debt"),
            sequences=without_channel(sequences, DEBT_CHANNEL),
        )
    if name == "lags_12":
        return replace(base, sequences=shorter(sequences, 12))
    if name == "lags_4":
        return replace(base, sequences=shorter(sequences, 4))
    if name == "no_sequence":
        return replace(base, sequences=np.full_like(sequences, np.nan))
    if name == "no_static":
        return replace(base, tweak=_no_static)
    if name == "no_masks":
        return replace(base, tweak=_all_observed)
    if name == "other_depth":
        layers = next(p.value for p in full.params if p.name == "layers")
        changed = tuple(
            Param(name="layers", value="2" if layers == "1" else "1") if p.name == "layers" else p
            for p in full.params
        )
        return replace(base, params=changed)
    raise ValueError(f"unknown ablation {name!r}")


def chosen_params(benchmark: BenchmarkReport, model: str) -> tuple[Param, ...]:
    return next(c.params for c in benchmark.configs if c.model == model)


def _memory(memory: Floats, row: int, q: Floats, labels: Floats, levels: tuple[float, ...]) -> None:
    for t in range(len(TARGETS)):
        for h in range(len(HORIZONS)):
            present = ~np.isnan(labels[:, t, h])
            if present.any():
                losses = pinball_rows(q[present, t, h], labels[present, t, h], levels)
                memory[row, t, h] += (losses.sum(), losses.size)


def train_variant(
    runner: Runner,
    variant: Variant,
    base: ForecastProtocol,
    protocol: EvaluationProtocol,
    sequences_id: str,
    config: Config,
    out: Path,
    progress: Callable[[str], None],
) -> Trainings:
    """Every fold of one variant; quantiles stay in the targets' training space."""
    levels, nominal, years = protocol.levels, protocol.nominal, base.test_years
    rows = year_rows(runner, years)
    position = np.full(runner.ds.years.size, -1)
    position[rows] = np.arange(rows.size)
    own = Runner(variant.dataset, base)
    bands = Bands.empty(rows.size, len(years), len(levels), len(nominal))
    keep_partial = variant.repeats > protocol.ablation_repeats
    partial = (
        Bands.empty(rows.size, len(years), len(levels), len(nominal)) if keep_partial else None
    )
    medians = np.full((variant.repeats, rows.size, len(TARGETS), len(HORIZONS)), np.nan, np.float32)
    memory = np.zeros((len(years), 2, len(TARGETS), len(HORIZONS), 2))
    runs: list[TrainingRun] = []
    middle = levels.index(0.5)
    for y, year in enumerate(years):
        current = fold(own, variant.sequences, year, config.seed)
        if variant.tweak is not None:
            current = variant.tweak(current)
        new_rows = np.flatnonzero(runner.ds.years == year)
        slots = position[new_rows]
        total_new: Floats | None = None
        total_watch: Floats | None = None
        for repeat in range(variant.repeats):
            setup = setting(config, variant.model, variant.params, protocol.seed + repeat)
            setup = replace(setup, levels=levels)
            trained = train(current.data, current.train_rows, current.valid_rows, setup)
            new = predict(trained.model, current.data, new_rows, setup, target_space=True)
            watch = predict(
                trained.model, current.data, current.valid_rows, setup, target_space=True
            )
            total_new = new if total_new is None else total_new + new
            total_watch = watch if total_watch is None else total_watch + watch
            medians[repeat, slots] = new[..., middle]
            if repeat == 0:
                fitted = predict(
                    trained.model, current.data, current.train_rows, setup, target_space=True
                )
                _memory(memory[y], 0, fitted, current.data.labels[current.train_rows], levels)
                _memory(memory[y], 1, watch, current.data.labels[current.valid_rows], levels)
            if partial is not None and repeat + 1 == protocol.ablation_repeats:
                partial.q[slots] = total_new / (repeat + 1)
            run, _ = save_run(
                own,
                sequences_id,
                current,
                trained,
                setup,
                out,
                smoke=False,
                max_train_rows=None,
                evaluated=new_rows.size,
                model=variant.name,
            )
            runs.append(run)
            progress(
                f"{variant.name} {year} seed {setup.seed}: {len(run.epochs)} epochs, "
                f"best {run.best_epoch}"
            )
        assert total_new is not None
        assert total_watch is not None
        bands.q[slots] = total_new / variant.repeats
        watch_mean = total_watch / variant.repeats
        labels = current.data.labels[current.valid_rows]
        for t in range(len(TARGETS)):
            for h in range(len(HORIZONS)):
                present = ~np.isnan(labels[:, t, h])
                if present.sum() == 0:
                    continue
                for n, level in enumerate(nominal):
                    bands.offsets[y, t, h, n] = conformal_offset(
                        watch_mean[present, t, h], labels[present, t, h], level, levels
                    )
    return Trainings(bands, runs, partial, medians, memory)


def input_conditions(
    runner: Runner, sequences: Floats, base: ForecastProtocol, ood_z: float, config: Config
) -> tuple[Floats, np.ndarray]:
    """Per scored row: observed quarters of the history, and whether its recent quarters
    lie beyond ``ood_z`` deviations of the fold's training rows."""
    years = base.test_years
    rows = year_rows(runner, years)
    position = np.full(runner.ds.years.size, -1)
    position[rows] = np.arange(rows.size)
    history = (~np.isnan(sequences[rows])).any(axis=2).sum(axis=1).astype(np.float64)
    outside = np.zeros(rows.size, dtype=bool)
    for year in years:
        current: Fold = fold(runner, sequences, year, config.seed)
        new_rows = np.flatnonzero(runner.ds.years == year)
        data: Arrays = current.data
        recent = (
            np.abs(data.values[new_rows, -RECENT_QUARTERS:])
            * data.mask[new_rows, -RECENT_QUARTERS:]
        )
        outside[position[new_rows]] = recent.max(axis=(1, 2)) > ood_z
    return history, outside


def _train_once(
    runner: Runner,
    variant: Variant,
    base: ForecastProtocol,
    protocol: EvaluationProtocol,
    sequences_id: str,
    config: Config,
    out: Path,
    progress: Callable[[str], None],
) -> None:
    """A stored variant is not trained again: a stopped run goes on where it stopped."""
    folder = out / "bands"
    if (folder / f"{variant.name}.npz").exists():
        return
    found = train_variant(
        runner, variant, base, protocol, sequences_id, config, out / "runs", progress
    )
    arrays: dict[str, np.ndarray] = {
        "rows": year_rows(runner, base.test_years),
        "q": found.bands.q,
        "offsets": found.bands.offsets,
        "medians": found.medians,
        "memory": found.memory,
        "checkpoints": np.array([r.checkpoint_sha256 for r in found.runs]),
    }
    if found.partial is not None:
        arrays["partial"] = found.partial.q
    save_arrays(folder, variant.name, arrays)


def run_trainings(
    dataset: Dataset,
    sequences: Floats,
    sequences_id: str,
    base: ForecastProtocol,
    protocol: EvaluationProtocol,
    benchmark: BenchmarkReport,
    config: Config,
    out: Path,
    progress: Callable[[str], None],
) -> None:
    """Both architectures, then the ablations of the one the development years choose."""
    runner = Runner(dataset, base)
    folder = out / "bands"
    years = len(base.test_years)
    planned = years * (
        len(NETWORKS) * protocol.repeats + len(protocol.ablations) * protocol.ablation_repeats
    )
    finished = 0

    def counted(line: str) -> None:
        """Every training line carries how much of the whole run is done."""
        nonlocal finished
        finished += 1
        progress(f"[{100 * finished / planned:3.0f}%] {line}")

    if not (folder / f"{CONDITIONS}.npz").exists():
        history, outside = input_conditions(runner, sequences, base, protocol.ood_z, config)
        save_arrays(folder, CONDITIONS, {"history": history, "outside": outside})
    fulls = {
        name: Variant(
            name, model, chosen_params(benchmark, model), protocol.repeats, dataset, sequences
        )
        for name, model in NETWORKS.items()
    }
    for variant in fulls.values():
        if (folder / f"{variant.name}.npz").exists():
            finished += years * variant.repeats
        _train_once(runner, variant, base, protocol, sequences_id, config, out, counted)
    stored = load_stored(folder)
    scope = scope_of(dataset, base, protocol, stored)
    primary, _, lines = choose_primary(scope, entries_of(stored, scope, base))
    for line in lines:
        progress(line)
    progress(f"ablations of {primary}")
    for name in protocol.ablations:
        variant = ablation(name, fulls[primary], protocol.ablation_repeats)
        if (folder / f"{variant.name}.npz").exists():
            finished += years * variant.repeats
        _train_once(runner, variant, base, protocol, sequences_id, config, out, counted)
