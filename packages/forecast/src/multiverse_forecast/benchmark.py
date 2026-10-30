"""The locked Stage 15 protocol: choose on validation, score the test period once.

- **Firms.** A seeded share of firms (``cold_start_share``) never enters training; they
  are scored as cold starts. The rest are the training firms.
- **Time.** Rolling origin with yearly refits. The model of fold year Y trains on the
  training firms' rows whose target was public before Y began (end of 31 December, US
  Eastern), so no target released later reaches it; it then forecasts the origins of Y.
- **Validation** folds are the years in ``validation_years``, scored only on targets
  public before the first test year; the setting with the lowest MAE over horizons 1, 4
  and 8 is chosen per target and model. **Test** folds are ``test_years``, scored with the
  chosen settings, for the training firms (test) and the held-out firms (cold start).
- **Rows.** Every model is scored on the same rows: target released and defined, and a
  persistence value at the origin, so each model's error can be set against persistence.
"""

import hashlib
import itertools
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    ForecastProtocol,
    ForecastTarget,
    ModelConfig,
    Param,
    Population,
    ScoreRow,
    SectorScore,
    SplitName,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_forecast.data import Bools, Dataset, Floats, canonical_sha256
from multiverse_forecast.models import Fold, applies, make, persistence_values
from multiverse_forecast.scoring import Errors, score, sector_scores

VALIDATION_HORIZONS = (1, 4, 8)
FAILURE_HORIZON = 4
FAILURES = 5
SECTOR_HORIZONS = (1, 4)
MIN_TRAIN = 200


def boundary(year: int) -> np.datetime64:
    """The end of 31 December of the year before, US Eastern (EST), in UTC."""
    return np.datetime64(f"{year}-01-01T05:00:00", "us")


def cold_start_firms(ciks: list[str], share: float, seed: int) -> set[str]:
    """Firms whose seeded hash falls below the share: stable across runs and machines."""
    limit = share * 2**256
    return {c for c in ciks if int(hashlib.sha256(f"{seed}:{c}".encode()).hexdigest(), 16) < limit}


@dataclass
class Prediction:
    rows: np.ndarray
    predicted: Floats


class Runner:
    def __init__(self, dataset: Dataset, protocol: ForecastProtocol) -> None:
        self.ds = dataset
        self.protocol = protocol
        unique = sorted(set(dataset.ciks.tolist()))
        self.held_out = cold_start_firms(unique, protocol.cold_start_share, protocol.seed)
        self.cold: Bools = np.isin(dataset.ciks, sorted(self.held_out))
        months = dataset.origins.astype("datetime64[M]").astype(np.int64) % 12
        self.quarters = dataset.years * 4 + months // 3
        self.weights = np.nan_to_num(dataset.rev_ttm)

    def scoreable(self, target: ForecastTarget, horizon: int) -> Bools:
        y = self.ds.targets[(target, horizon)].value
        naive = persistence_values(self.ds.x, self.ds.features, target)
        return ~np.isnan(y) & ~np.isnan(naive)

    def fold(
        self, target: ForecastTarget, horizon: int, year: int, rows: np.ndarray
    ) -> Fold | None:
        t = self.ds.targets[(target, horizon)]
        train = ~self.cold & ~np.isnan(t.value) & (t.released <= boundary(year))
        if train.sum() < MIN_TRAIN or rows.size == 0:
            return None
        return Fold(
            target=target,
            horizon=horizon,
            features=self.ds.features,
            x_train=self.ds.x[train],
            y_train=t.value[train],
            divisions_train=self.ds.divisions[train],
            quarters_train=self.quarters[train],
            x_eval=self.ds.x[rows],
            divisions_eval=self.ds.divisions[rows],
            quantile=self.protocol.winsor_quantile,
            seed=self.protocol.seed,
        )

    def predict(
        self,
        name: str,
        params: tuple[Param, ...],
        target: ForecastTarget,
        horizon: int,
        years: tuple[int, ...],
        eligible: Bools,
    ) -> Prediction:
        rows_all: list[np.ndarray] = []
        predicted: list[Floats] = []
        for year in years:
            rows = np.flatnonzero(eligible & (self.ds.years == year))
            fold = self.fold(target, horizon, year, rows)
            if fold is None:
                continue
            model = make(name, params)
            model.fit(fold)
            rows_all.append(rows)
            predicted.append(model.predict(fold))
        if not rows_all:
            return Prediction(np.zeros(0, dtype=np.int64), np.zeros(0))
        return Prediction(np.concatenate(rows_all), np.concatenate(predicted))

    def scores(
        self, target: ForecastTarget, horizon: int, split: SplitName, model: str, p: Prediction
    ) -> list[ScoreRow]:
        """The scores of all rows, and of the firms with material revenue at the origin."""
        found = []
        material = self.weights[p.rows] >= self.protocol.material_revenue
        for population, mask in ((Population.ALL, None), (Population.MATERIAL, material)):
            part = p if mask is None else Prediction(p.rows[mask], p.predicted[mask])
            if part.rows.size == 0:
                continue
            errors = self.errors(target, horizon, part)
            found.append(
                score(
                    target,
                    horizon,
                    split,
                    model,
                    errors,
                    self.protocol.bootstrap_resamples,
                    self.protocol.seed,
                    population,
                )
            )
        return found

    def errors(self, target: ForecastTarget, horizon: int, p: Prediction) -> Errors:
        rows = p.rows
        return Errors(
            ciks=self.ds.ciks[rows],
            divisions=self.ds.divisions[rows],
            weights=self.weights[rows],
            actual=self.ds.targets[(target, horizon)].value[rows],
            predicted=p.predicted,
            naive=persistence_values(self.ds.x[rows], self.ds.features, target),
        )


def run(dataset: Dataset, protocol: ForecastProtocol, protocol_sha256: str) -> BenchmarkReport:
    runner = Runner(dataset, protocol)
    seed = protocol.seed
    validation_end = boundary(min(protocol.test_years))
    configs: list[ModelConfig] = []
    scores: list[ScoreRow] = []
    sectors: list[SectorScore] = []
    worst: dict[tuple[ForecastTarget, str], tuple[float, list[str]]] = {}
    for target in protocol.targets:
        for name, grid in protocol.grids.items():
            if not applies(name, target):
                continue
            best: tuple[float, tuple[Param, ...], dict[int, Prediction]] | None = None
            for params in grid:
                found: dict[int, Prediction] = {}
                absolute: list[Floats] = []
                for horizon in (h for h in VALIDATION_HORIZONS if h in protocol.horizons):
                    t = dataset.targets[(target, horizon)]
                    eligible = runner.scoreable(target, horizon) & ~runner.cold
                    eligible &= t.released <= validation_end
                    p = runner.predict(
                        name, params, target, horizon, protocol.validation_years, eligible
                    )
                    found[horizon] = p
                    absolute.append(np.abs(p.predicted - t.value[p.rows]))
                pooled = np.concatenate(absolute) if absolute else np.zeros(0)
                if pooled.size == 0:
                    continue
                mae = float(pooled.mean())
                if best is None or mae < best[0]:
                    best = (mae, params, found)
            if best is None:
                continue
            mae, params, found = best
            configs.append(
                ModelConfig(target=target, model=name, params=params, validation_mae=mae)
            )
            for horizon, p in found.items():
                if p.rows.size:
                    scores += runner.scores(target, horizon, SplitName.VALIDATION, name, p)
            for horizon in protocol.horizons:
                eligible = runner.scoreable(target, horizon)
                p = runner.predict(name, params, target, horizon, protocol.test_years, eligible)
                if p.rows.size == 0:
                    continue
                cold = runner.cold[p.rows]
                for split, mask in ((SplitName.TEST, ~cold), (SplitName.COLD_START, cold)):
                    if not mask.any():
                        continue
                    part = Prediction(p.rows[mask], p.predicted[mask])
                    errors = runner.errors(target, horizon, part)
                    scores += runner.scores(target, horizon, split, name, part)
                    if horizon in SECTOR_HORIZONS:
                        sectors += sector_scores(target, horizon, split, name, errors)
                    if horizon == FAILURE_HORIZON and split is SplitName.TEST:
                        worst[(target, name)] = (
                            float(np.abs(errors.predicted - errors.actual).mean()),
                            failure_cases(runner, part, target),
                        )
    findings = summarize(scores, protocol)
    failures: list[str] = []
    for target in protocol.targets:
        mine = {m: v for (t, m), v in worst.items() if t is target and m != "persistence"}
        if mine:
            model = min(mine, key=lambda m: mine[m][0])
            failures += [
                f"{target.value} h={FAILURE_HORIZON} {model}: {line}" for line in mine[model][1]
            ]
    payload = {
        "dataset": dataset.manifest.sha256,
        "protocol": protocol_sha256,
        "configs": [c.model_dump(mode="json") for c in configs],
        "scores": [s.model_dump(mode="json") for s in scores],
        "sectors": [s.model_dump(mode="json") for s in sectors],
    }
    digest = canonical_sha256(payload)
    return BenchmarkReport(
        # The date of the dataset id: the data cutoff as a US Eastern date.
        benchmark_id=f"bench-{dataset.manifest.dataset_id.split('-')[1]}-{digest[:12]}",
        sha256=digest,
        dataset_id=dataset.manifest.dataset_id,
        dataset_sha256=dataset.manifest.sha256,
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol_sha256,
        seed=seed,
        configs=tuple(configs),
        scores=tuple(scores),
        sectors=tuple(sectors),
        findings=tuple(findings),
        failures=tuple(failures),
        contracts_version=CONTRACTS_VERSION,
        created_at=datetime.now(UTC),
    )


def failure_cases(runner: Runner, p: Prediction, target: ForecastTarget) -> list[str]:
    """The largest errors of one model: company, origin, what happened, what it said."""
    actual = runner.ds.targets[(target, FAILURE_HORIZON)].value[p.rows]
    order = np.argsort(-np.abs(p.predicted - actual))[:FAILURES]
    return [
        f"CIK {runner.ds.ciks[p.rows[i]]} origin {runner.ds.origins[p.rows[i]]}: actual "
        f"{actual[i]:.4g}, forecast {p.predicted[i]:.4g}"
        for i in order
    ]


def summarize(scores: list[ScoreRow], protocol: ForecastProtocol) -> list[str]:
    """Per population, target and horizon of the test split: which models beat persistence."""
    lines: list[str] = []
    for population, target, horizon in itertools.product(
        Population, protocol.targets, protocol.horizons
    ):
        rows = [
            s
            for s in scores
            if s.target is target
            and s.horizon == horizon
            and s.split is SplitName.TEST
            and s.population is population
        ]
        others = [s for s in rows if s.model != "persistence"]
        if not others:
            continue
        better = [s.model for s in others if s.vs_naive_high is not None and s.vs_naive_high < 0]
        worse = [s.model for s in others if s.vs_naive is not None and s.vs_naive >= 0]
        best = min(others, key=lambda s: s.mae)
        change = f"{100 * best.vs_naive:+.1f}%" if best.vs_naive is not None else "n/a"
        typical = min(rows, key=lambda s: s.median_ae)
        naive = next((s for s in rows if s.model == "persistence"), None)
        median = f"persistence {naive.median_ae:.3g}, " if naive is not None else ""
        lines.append(
            f"{target.value} h={horizon} ({population.value}): best {best.model} "
            f"(MAE {best.mae:.4g}, {change} vs persistence); {len(better)} of {len(others)} "
            f"models beat persistence with the 95% interval below zero; not better: "
            f"{', '.join(worse) or 'none'}; median AE: {median}lowest {typical.model} "
            f"{typical.median_ae:.3g}"
        )
    return lines or ["no test rows"]
