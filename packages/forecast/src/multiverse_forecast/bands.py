"""Quantile bands: how they are stored, and the baselines' own bands (Stage 17).

A band holds, for the rows of the test years, quantiles at the protocol's levels in each
target's training space, plus the conformal offsets of its fold. The baselines get the
same treatment as the network, on the same split of the fold's labels:

- rows of the training firms outside the watch set fit the model;
- rows of the watch set (a seeded tenth of the training firms) calibrate it; the network
  only used them to stop its training.

``persistence``, ``elastic_net`` and ``gbm`` add the empirical quantiles of their errors
on the watch rows to their point forecast: one spread for every firm, calibrated by
construction. ``gbm_quantile`` is the fair rival: gradient boosting trained on the pinball
loss, one model per level, so its spread depends on the firm, like the network's.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    EvaluationProtocol,
    ForecastTarget,
    Param,
)
from multiverse_forecast.benchmark import MIN_TRAIN, Runner, boundary, watch_rows
from multiverse_forecast.data import Floats
from multiverse_forecast.models import Fold, Prep, make, persistence_values
from multiverse_forecast.probabilistic import conformal_offset, to_target_space

TARGETS = tuple(ForecastTarget)
HORIZONS = (1, 4, 8, 12, 20)
MIN_CALIBRATION = 30
RESIDUAL_MODELS = ("persistence", "elastic_net", "gbm")
QUANTILE_MODEL = "gbm_quantile"
BASELINE_BANDS = (*RESIDUAL_MODELS, QUANTILE_MODEL)
NETWORKS = {"gru_attention_q7": "gru_attention", "tcn_q7": "tcn"}
CONDITIONS = "conditions"
PARTIAL = ".partial"


@dataclass
class Bands:
    q: Floats
    """[rows of the test years, targets, horizons, levels]; NaN where nothing was forecast."""
    offsets: Floats
    """[test years, targets, horizons, nominal coverages]; zero where calibrated already."""

    @classmethod
    def empty(cls, rows: int, years: int, levels: int, nominal: int) -> "Bands":
        return cls(
            np.full((rows, len(TARGETS), len(HORIZONS), levels), np.nan, dtype=np.float32),
            np.zeros((years, len(TARGETS), len(HORIZONS), nominal)),
        )


@dataclass(frozen=True)
class Stored:
    """What the trainings left: bands by name, and the measures taken while training."""

    rows: np.ndarray
    bands: dict[str, Bands]
    history: np.ndarray
    """Observed quarters of each row's 24."""
    outside: np.ndarray
    """Whether a recent quarter of the row lies outside the fold's training rows."""
    medians: dict[str, np.ndarray]
    memory: dict[str, np.ndarray]
    checkpoints: dict[str, list[str]]
    sha256: str


def year_rows(runner: Runner, years: tuple[int, ...]) -> np.ndarray:
    return np.flatnonzero(np.isin(runner.ds.years, years))


def save_arrays(folder: Path, name: str, arrays: dict[str, np.ndarray]) -> None:
    """One compressed file per band, written whole: a stopped run leaves no half band."""
    folder.mkdir(parents=True, exist_ok=True)
    pending = folder / f"{name}.pending"
    with pending.open("wb") as handle:
        np.savez_compressed(handle, **arrays)  # type: ignore[arg-type,unused-ignore]
    pending.replace(folder / f"{name}.npz")


def load_stored(folder: Path) -> Stored:
    """Every stored band; a band's own rows must be the rows of the others."""
    digest = hashlib.sha256()
    rows: np.ndarray | None = None
    bands: dict[str, Bands] = {}
    medians: dict[str, np.ndarray] = {}
    memory: dict[str, np.ndarray] = {}
    checkpoints: dict[str, list[str]] = {}
    history, outside = np.zeros(0), np.zeros(0, dtype=bool)
    for path in sorted(folder.glob("*.npz")):
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        with np.load(path) as found:
            if path.stem == CONDITIONS:
                history, outside = found["history"], found["outside"]
                continue
            if rows is not None and not np.array_equal(rows, found["rows"]):
                raise ValueError(f"{path}: other rows than the bands before it")
            rows = found["rows"]
            name = path.stem
            bands[name] = Bands(found["q"], found["offsets"])
            if "partial" in found.files:
                bands[name + PARTIAL] = Bands(found["partial"], found["offsets"])
            if "medians" in found.files:
                medians[name] = found["medians"]
                memory[name] = found["memory"]
            if "checkpoints" in found.files:
                checkpoints[name] = [str(c) for c in found["checkpoints"]]
    if rows is None:
        raise ValueError(f"{folder}: no stored bands")
    return Stored(rows, bands, history, outside, medians, memory, checkpoints, digest.hexdigest())


def _params(report: BenchmarkReport, target: ForecastTarget, model: str) -> tuple[Param, ...]:
    return next(c.params for c in report.configs if c.target is target and c.model == model)


def residual_band(
    point_calibration: Floats, y: Floats, point_new: Floats, levels: tuple[float, ...]
) -> Floats:
    """The point forecast plus the quantiles of its errors on the calibration rows."""
    usable = ~np.isnan(point_calibration)
    return point_new[:, None] + np.quantile(y[usable] - point_calibration[usable], levels)


def quantile_gbm(
    fold: Fold, y_train: Floats, params: tuple[Param, ...], levels: tuple[float, ...]
) -> Floats:
    """One gradient-boosted model per level on the pinball loss; sorted, so none cross."""
    values = {p.name: float(p.value) for p in params}
    prep = Prep(fold.quantile, impute=False, scale=False).fit(
        fold.x_train, fold.features, fold.divisions_train
    )
    design = prep.transform(fold.x_train, fold.divisions_train)
    new = prep.transform(fold.x_eval, fold.divisions_eval)
    found = []
    for level in levels:
        model = HistGradientBoostingRegressor(
            loss="quantile",
            quantile=level,
            max_depth=int(values["max_depth"]),
            learning_rate=values["learning_rate"],
            max_iter=int(values["max_iter"]),
            min_samples_leaf=int(values["min_samples_leaf"]),
            early_stopping=False,
            random_state=fold.seed,
        )
        model.fit(design, y_train)
        found.append(np.asarray(model.predict(new), dtype=np.float64))
    return np.sort(np.stack(found, axis=1), axis=1)


def baseline_bands(
    runner: Runner,
    report: BenchmarkReport,
    protocol: EvaluationProtocol,
    years: tuple[int, ...],
    progress: Callable[[str], None] = print,
) -> tuple[np.ndarray, dict[str, Bands]]:
    """Every baseline band of every fold, each fitted and calibrated before its year."""
    ds = runner.ds
    rows = year_rows(runner, years)
    position = np.full(ds.years.size, -1)
    position[rows] = np.arange(rows.size)
    levels, nominal = protocol.levels, protocol.nominal
    bands = {
        n: Bands.empty(rows.size, len(years), len(levels), len(nominal)) for n in BASELINE_BANDS
    }
    watched = watch_rows(runner)
    for y, year in enumerate(years):
        new_rows = np.flatnonzero(ds.years == year)
        slots = position[new_rows]
        for t, target in enumerate(TARGETS):
            for h, horizon in enumerate(HORIZONS):
                found = ds.targets[(target, horizon)]
                known = ~runner.cold & ~np.isnan(found.value) & (found.released <= boundary(year))
                fit_rows = np.flatnonzero(known & ~watched)
                cal_rows = np.flatnonzero(known & watched)
                if fit_rows.size < MIN_TRAIN or cal_rows.size < MIN_CALIBRATION:
                    continue
                y_cal = to_target_space(target, found.value[cal_rows])
                both = np.concatenate([cal_rows, new_rows])
                fold = Fold(
                    target=target,
                    horizon=horizon,
                    features=ds.features,
                    x_train=ds.x[fit_rows],
                    y_train=found.value[fit_rows],
                    divisions_train=ds.divisions[fit_rows],
                    quarters_train=runner.quarters[fit_rows],
                    x_eval=ds.x[both],
                    divisions_eval=ds.divisions[both],
                    quantile=runner.protocol.winsor_quantile,
                    seed=runner.protocol.seed,
                )
                for name in RESIDUAL_MODELS:
                    if name == "persistence":
                        raw = persistence_values(ds.x[both], ds.features, target)
                    else:
                        model = make(name, _params(report, target, name))
                        model.fit(fold)
                        raw = model.predict(fold)
                    point = to_target_space(target, raw)
                    band = residual_band(
                        point[: cal_rows.size], y_cal, point[cal_rows.size :], levels
                    )
                    bands[name].q[slots, t, h] = band
                spread = quantile_gbm(
                    fold,
                    to_target_space(target, found.value[fit_rows]),
                    _params(report, target, "gbm"),
                    levels,
                )
                bands[QUANTILE_MODEL].q[slots, t, h] = spread[cal_rows.size :]
                for n, level in enumerate(nominal):
                    bands[QUANTILE_MODEL].offsets[y, t, h, n] = conformal_offset(
                        spread[: cal_rows.size], y_cal, level, levels
                    )
        progress(f"baselines {year} done")
    return rows, bands


def run_baselines(
    runner: Runner,
    report: BenchmarkReport,
    protocol: EvaluationProtocol,
    years: tuple[int, ...],
    folder: Path,
    progress: Callable[[str], None] = print,
) -> None:
    rows, bands = baseline_bands(runner, report, protocol, years, progress)
    for name, band in bands.items():
        save_arrays(folder, name, {"rows": rows, "q": band.q, "offsets": band.offsets})
