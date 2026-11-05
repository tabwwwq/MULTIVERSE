"""Stage 17 measures: every band on the same rows, sliced, with firm-bootstrap intervals.

The rows are those of Stage 15 (target released and defined, a persistence value at the
origin) on which every stored band has a forecast. Scores are in each target's training
space; the median error also in its own units, as in Stages 15 and 16.
"""

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from multiverse_contracts.forecasting import (
    AblationScore,
    ApprovalRow,
    BandScore,
    CompanyErrors,
    EvaluationProtocol,
    ForecastProtocol,
    ForecastTarget,
    MemorizationScore,
    Population,
    SliceScore,
    SplitName,
    StabilityScore,
)
from multiverse_forecast.bands import (
    BASELINE_BANDS,
    HORIZONS,
    NETWORKS,
    QUANTILE_MODEL,
    TARGETS,
    Bands,
    Stored,
)
from multiverse_forecast.benchmark import Runner
from multiverse_forecast.data import Bools, Dataset, Floats
from multiverse_forecast.models import persistence_values
from multiverse_forecast.probabilistic import (
    conformalize,
    covered,
    firm_interval,
    firm_ratio_draws,
    from_target_space,
    pinball_rows,
    ratio_interval,
    reliability,
    to_target_space,
    widths,
    wis_rows,
)

MIN_ROWS = 30
PERIODS = ("development", "final", "all")
SLICE_HORIZONS = (1, 4, 8)
COMPANY_HORIZONS = (1, 4)
STABILITY_PAIRS = ((8, 4), (4, 1), (12, 8), (20, 12))
ABLATION_HORIZONS = (1, 4, 8)
ARCHITECTURES = tuple(NETWORKS)


@dataclass(frozen=True)
class Entry:
    """A band as it is scored: a model, calibrated or not."""

    model: str
    calibrated: bool
    q: Floats


@dataclass
class Scope:
    runner: Runner
    base: ForecastProtocol
    protocol: EvaluationProtocol
    rows: np.ndarray
    common: Bools
    """[rows, targets, horizons]: scoreable, and every band has a forecast."""
    values: dict[tuple[ForecastTarget, int], Floats] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for target, horizon in itertools.product(TARGETS, HORIZONS):
            self.values[(target, horizon)] = self.runner.ds.targets[(target, horizon)].value[
                self.rows
            ]

    @property
    def years(self) -> np.ndarray:
        return np.asarray(self.runner.ds.years[self.rows])

    @property
    def ciks(self) -> np.ndarray:
        return np.asarray(self.runner.ds.ciks[self.rows])

    def period_years(self, period: str) -> tuple[int, ...]:
        if period == "development":
            return self.protocol.development_years
        if period == "final":
            return self.protocol.final_years
        return (*self.protocol.development_years, *self.protocol.final_years)

    def select(
        self,
        target: ForecastTarget,
        horizon: int,
        split: SplitName,
        population: Population,
        period: str,
    ) -> np.ndarray:
        cold = self.runner.cold[self.rows]
        mask = self.common[:, TARGETS.index(target), HORIZONS.index(horizon)].copy()
        mask &= cold if split is SplitName.COLD_START else ~cold
        mask &= np.isin(self.years, self.period_years(period))
        if population is Population.MATERIAL:
            mask &= self.runner.weights[self.rows] >= self.base.material_revenue
        return np.flatnonzero(mask)

    def actual(self, target: ForecastTarget, horizon: int, chosen: np.ndarray) -> Floats:
        return to_target_space(target, self.values[(target, horizon)][chosen])

    def persistence_error(self, target: ForecastTarget, horizon: int, chosen: np.ndarray) -> Floats:
        """Absolute error of plain persistence in the target's own units."""
        x = self.runner.ds.x[self.rows[chosen]]
        naive = persistence_values(x, self.runner.ds.features, target)
        return np.asarray(np.abs(naive - self.values[(target, horizon)][chosen]))


def common_rows(runner: Runner, rows: np.ndarray, bands: Sequence[Bands]) -> Bools:
    mask = np.zeros((rows.size, len(TARGETS), len(HORIZONS)), dtype=bool)
    for (t, target), (h, horizon) in itertools.product(enumerate(TARGETS), enumerate(HORIZONS)):
        mask[:, t, h] = runner.scoreable(target, horizon)[rows]
    for band in bands:
        mask &= ~np.isnan(band.q).any(axis=-1)
    return mask


def calibrated(
    band: Bands, years: np.ndarray, test_years: tuple[int, ...], protocol: EvaluationProtocol
) -> Floats:
    """The quantiles of a band after the conformal offsets of each fold."""
    out = band.q.astype(np.float64)
    for y, year in enumerate(test_years):
        slots = np.flatnonzero(years == year)
        for t, h in itertools.product(range(len(TARGETS)), range(len(HORIZONS))):
            part = out[slots, t, h]
            known = ~np.isnan(part).any(axis=1)
            if known.any():
                offsets = dict(zip(protocol.nominal, band.offsets[y, t, h], strict=True))
                part[known] = conformalize(part[known], offsets, protocol.levels)
                out[slots, t, h] = part
    return out


def scope_of(
    dataset: Dataset, base: ForecastProtocol, protocol: EvaluationProtocol, stored: Stored
) -> Scope:
    runner = Runner(dataset, base)
    scored = [b for n, b in stored.bands.items() if n in (*ARCHITECTURES, *BASELINE_BANDS)]
    return Scope(runner, base, protocol, stored.rows, common_rows(runner, stored.rows, scored))


def entries_of(
    stored: Stored, scope: Scope, base: ForecastProtocol
) -> dict[tuple[str, bool], Entry]:
    """Every stored band as it is scored: spreads learned per firm raw and calibrated, the
    residual bands as they are, calibrated by construction."""
    found: dict[tuple[str, bool], Entry] = {}
    for name in (*ARCHITECTURES, QUANTILE_MODEL):
        if name in stored.bands:
            band = stored.bands[name]
            found[(name, False)] = Entry(name, False, band.q.astype(np.float64))
            found[(name, True)] = Entry(
                name, True, calibrated(band, scope.years, base.test_years, scope.protocol)
            )
    for name in BASELINE_BANDS:
        if name != QUANTILE_MODEL and name in stored.bands:
            found[(name, True)] = Entry(name, True, stored.bands[name].q.astype(np.float64))
    return found


def _q(entry: Entry, target: ForecastTarget, horizon: int, chosen: np.ndarray) -> Floats:
    return np.asarray(entry.q[chosen, TARGETS.index(target), HORIZONS.index(horizon)])


def choose_primary(
    scope: Scope, entries: dict[tuple[str, bool], Entry]
) -> tuple[str, bool, list[str]]:
    """On the development years only: the architecture with the lowest pinball, and
    calibration if it brings coverage closer to nominal."""
    protocol = scope.protocol
    lines: list[str] = []
    logs: dict[tuple[str, bool], float] = {}
    gaps: dict[tuple[str, bool], float] = {}
    for (model, flag), entry in entries.items():
        if model not in ARCHITECTURES:
            continue
        pinballs: list[float] = []
        gap: list[float] = []
        for target, horizon in itertools.product(TARGETS, HORIZONS):
            chosen = scope.select(target, horizon, SplitName.TEST, Population.ALL, "development")
            if chosen.size < MIN_ROWS:
                continue
            q, y = _q(entry, target, horizon, chosen), scope.actual(target, horizon, chosen)
            pinballs.append(float(pinball_rows(q, y, protocol.levels).mean()))
            gap += [
                abs(float(covered(q, y, n, protocol.levels).mean()) - n) for n in protocol.nominal
            ]
        logs[(model, flag)] = float(np.mean(np.log(pinballs)))
        gaps[(model, flag)] = float(np.mean(gap))
        lines.append(
            f"development years, {model} {'calibrated' if flag else 'raw'}: mean log pinball "
            f"{logs[(model, flag)]:.4f}, mean coverage gap {gaps[(model, flag)]:.4f}"
        )
    primary = min(ARCHITECTURES, key=lambda m: min(logs[(m, False)], logs[(m, True)]))
    return primary, gaps[(primary, True)] < gaps[(primary, False)], lines


def band_scores(scope: Scope, entries: dict[tuple[str, bool], Entry]) -> list[BandScore]:
    protocol, seed = scope.protocol, scope.protocol.seed
    resamples = scope.base.bootstrap_resamples
    levels, nominal = protocol.levels, protocol.nominal
    middle = levels.index(0.5)
    found: list[BandScore] = []
    cells = itertools.product(
        TARGETS,
        HORIZONS,
        (SplitName.TEST, SplitName.COLD_START),
        Population,
        PERIODS,
    )
    for target, horizon, split, population, period in cells:
        chosen = scope.select(target, horizon, split, population, period)
        if chosen.size < MIN_ROWS:
            continue
        y = scope.actual(target, horizon, chosen)
        own = scope.values[(target, horizon)][chosen]
        ciks = scope.ciks[chosen]
        losses = {
            key: pinball_rows(_q(entry, target, horizon, chosen), y, levels)
            for key, entry in entries.items()
        }
        reference = losses[("persistence", True)]
        rivals = [k for k in losses if k[0] in BASELINE_BANDS and k[1]]
        best = min(rivals, key=lambda k: float(losses[k].mean()))
        for key, entry in entries.items():
            q = _q(entry, target, horizon, chosen)
            loss = losses[key]
            low, high = firm_interval(ciks, loss, resamples, seed)
            hits = [covered(q, y, n, levels).astype(np.float64) for n in nominal]
            spans = [firm_interval(ciks, hit, resamples, seed) for hit in hits]
            median = from_target_space(target, q[:, middle])
            relative: dict[str, float | str | None] = {}
            if key != ("persistence", True):
                change, c_low, c_high = ratio_interval(ciks, loss, reference, resamples, seed)
                relative |= {
                    "vs_persistence": change,
                    "vs_persistence_low": c_low,
                    "vs_persistence_high": c_high,
                }
            if key[0] not in BASELINE_BANDS:
                change, c_low, c_high = ratio_interval(ciks, loss, losses[best], resamples, seed)
                relative |= {
                    "vs_best": change,
                    "vs_best_low": c_low,
                    "vs_best_high": c_high,
                    "best_baseline": best[0],
                }
            found.append(
                BandScore(
                    target=target,
                    horizon=horizon,
                    split=split,
                    population=population,
                    period=period,
                    model=entry.model,
                    calibrated=entry.calibrated,
                    examples=int(chosen.size),
                    companies=len(set(ciks.tolist())),
                    pinball=float(loss.mean()),
                    pinball_low=low,
                    pinball_high=high,
                    wis=float(wis_rows(q, y, levels).mean()),
                    median_ae=float(np.median(np.abs(median - own))),
                    coverage=tuple(float(hit.mean()) for hit in hits),
                    coverage_low=tuple(s[0] for s in spans),
                    coverage_high=tuple(s[1] for s in spans),
                    width=tuple(float(widths(q, n, levels).mean()) for n in nominal),
                    median_width=tuple(float(np.median(widths(q, n, levels))) for n in nominal),
                    reliability=tuple(float(v) for v in reliability(q, y)),
                    **relative,  # type: ignore[arg-type]
                )
            )
    return found


def slice_scores(
    scope: Scope, entry: Entry, reference: Entry, history: Floats, outside: np.ndarray
) -> list[SliceScore]:
    """The primary model on each year, sector, history length and input condition."""
    protocol = scope.protocol
    ds = scope.runner.ds
    groups: list[tuple[str, str, Bools]] = [
        ("year", str(year), scope.years == year) for year in scope.base.test_years
    ]
    divisions = ds.divisions[scope.rows]
    groups += [("division", str(d), divisions == d) for d in sorted(set(divisions.tolist()))]
    groups += [
        ("history", "sparse", history < protocol.sparse_quarters),
        (
            "history",
            "medium",
            (history >= protocol.sparse_quarters) & (history < protocol.dense_quarters),
        ),
        ("history", "dense", history >= protocol.dense_quarters),
        ("distribution", "inside", ~outside),
        ("distribution", "outside", outside),
    ]
    found: list[SliceScore] = []
    for target, horizon in itertools.product(TARGETS, SLICE_HORIZONS):
        everyone = scope.select(target, horizon, SplitName.TEST, Population.ALL, "all")
        for kind, value, mask in groups:
            chosen = everyone[mask[everyone]]
            if chosen.size < MIN_ROWS:
                continue
            q, y = _q(entry, target, horizon, chosen), scope.actual(target, horizon, chosen)
            mine = float(pinball_rows(q, y, protocol.levels).mean())
            other = pinball_rows(_q(reference, target, horizon, chosen), y, protocol.levels)
            found.append(
                SliceScore(
                    kind=kind,  # type: ignore[arg-type]
                    value=value,
                    target=target,
                    horizon=horizon,
                    model=entry.model,
                    examples=int(chosen.size),
                    companies=len(set(scope.ciks[chosen].tolist())),
                    pinball=mine,
                    vs_persistence=mine / float(other.mean()) - 1,
                    coverage=tuple(
                        float(covered(q, y, n, protocol.levels).mean()) for n in protocol.nominal
                    ),
                )
            )
    return found


def company_errors(scope: Scope, entry: Entry, reference: Entry) -> list[CompanyErrors]:
    levels = scope.protocol.levels
    found: list[CompanyErrors] = []
    for target, horizon in itertools.product(TARGETS, COMPANY_HORIZONS):
        chosen = scope.select(target, horizon, SplitName.TEST, Population.ALL, "all")
        if chosen.size < MIN_ROWS:
            continue
        y = scope.actual(target, horizon, chosen)
        mine = pinball_rows(_q(entry, target, horizon, chosen), y, levels)
        other = pinball_rows(_q(reference, target, horizon, chosen), y, levels)
        _, index = np.unique(scope.ciks[chosen], return_inverse=True)
        counts = np.bincount(index).astype(np.float64)
        firm_mine = np.bincount(index, weights=mine) / counts
        firm_other = np.bincount(index, weights=other) / counts
        found.append(
            CompanyErrors(
                target=target,
                horizon=horizon,
                model=entry.model,
                companies=int(counts.size),
                examples=int(chosen.size),
                examples_per_firm_median=float(np.median(counts)),
                pinball_p10=float(np.quantile(firm_mine, 0.1)),
                pinball_p50=float(np.quantile(firm_mine, 0.5)),
                pinball_p90=float(np.quantile(firm_mine, 0.9)),
                better_than_persistence=float((firm_mine < firm_other).mean()),
            )
        )
    return found


def ablation_scores(
    scope: Scope, partner: Entry, variants: dict[str, Entry]
) -> list[AblationScore]:
    levels, resamples = scope.protocol.levels, scope.base.bootstrap_resamples
    found: list[AblationScore] = []
    for name, entry in variants.items():
        for target, horizon in itertools.product(TARGETS, ABLATION_HORIZONS):
            chosen = scope.select(target, horizon, SplitName.TEST, Population.ALL, "all")
            if chosen.size < MIN_ROWS:
                continue
            y = scope.actual(target, horizon, chosen)
            mine = pinball_rows(_q(entry, target, horizon, chosen), y, levels)
            full = pinball_rows(_q(partner, target, horizon, chosen), y, levels)
            change, low, high = ratio_interval(
                scope.ciks[chosen], mine, full, resamples, scope.protocol.seed
            )
            found.append(
                AblationScore(
                    name=name,
                    target=target,
                    horizon=horizon,
                    examples=int(chosen.size),
                    pinball=float(mine.mean()),
                    change=change,
                    change_low=low,
                    change_high=high,
                )
            )
    return found


def memorization_scores(
    scope: Scope, entry: Entry, reference: Entry, memory: Floats
) -> list[MemorizationScore]:
    levels, resamples = scope.protocol.levels, scope.base.bootstrap_resamples
    seed = scope.protocol.seed
    found: list[MemorizationScore] = []
    for (t, target), (h, horizon) in itertools.product(enumerate(TARGETS), enumerate(HORIZONS)):
        seen = scope.select(target, horizon, SplitName.TEST, Population.ALL, "all")
        cold = scope.select(target, horizon, SplitName.COLD_START, Population.ALL, "all")
        sums = memory[:, :, t, h].sum(axis=0)
        if seen.size < MIN_ROWS or cold.size < MIN_ROWS or (sums[:, 1] == 0).any():
            continue
        parts = []
        for chosen in (seen, cold):
            y = scope.actual(target, horizon, chosen)
            mine = pinball_rows(_q(entry, target, horizon, chosen), y, levels)
            other = pinball_rows(_q(reference, target, horizon, chosen), y, levels)
            parts.append((mine, other, scope.ciks[chosen]))
        (seen_mine, seen_other, seen_ciks), (cold_mine, cold_other, cold_ciks) = parts
        boot = firm_ratio_draws(cold_ciks, cold_mine, cold_other, resamples, seed) / (
            firm_ratio_draws(seen_ciks, seen_mine, seen_other, resamples, seed + 1)
        )
        found.append(
            MemorizationScore(
                target=target,
                horizon=horizon,
                trained=float(sums[0, 0] / sums[0, 1]),
                watched=float(sums[1, 0] / sums[1, 1]),
                test_seen=float(seen_mine.mean()),
                test_cold=float(cold_mine.mean()),
                cold_change=float(
                    (cold_mine.mean() / cold_other.mean()) / (seen_mine.mean() / seen_other.mean())
                    - 1
                ),
                cold_change_low=float(np.quantile(boot - 1, 0.025)),
                cold_change_high=float(np.quantile(boot - 1, 0.975)),
            )
        )
    return found


def stability_scores(scope: Scope, entry: Entry, medians: Floats) -> list[StabilityScore]:
    """A direct model has no recursive rollout; what can wobble is the forecast of one
    quarter as its origin moves closer, and the forecast between seeds."""
    middle = scope.protocol.levels.index(0.5)
    ds = scope.runner.ds
    months = ds.origins[scope.rows].astype("datetime64[M]").astype(np.int64)
    quarters = months // 3
    index = {(c, int(k)): i for i, (c, k) in enumerate(zip(scope.ciks, quarters, strict=True))}
    found: list[StabilityScore] = []
    for target, (long, short) in itertools.product(TARGETS, STABILITY_PAIRS):
        t, h_long, h_short = (
            TARGETS.index(target),
            HORIZONS.index(long),
            HORIZONS.index(short),
        )
        early, late = [], []
        for i, (cik, quarter) in enumerate(zip(scope.ciks, quarters, strict=True)):
            j = index.get((cik, int(quarter) + long - short))
            if j is not None and scope.common[i, t, h_long] and scope.common[j, t, h_short]:
                early.append(i)
                late.append(j)
        if len(early) < MIN_ROWS:
            continue
        first, second = np.array(early), np.array(late)
        revision = np.abs(entry.q[first, t, h_long, middle] - entry.q[second, t, h_short, middle])
        actual = to_target_space(target, scope.values[(target, short)][second])
        error = np.abs(entry.q[second, t, h_short, middle] - actual)
        spread = medians[:, first, t, h_long].std(axis=0)
        found.append(
            StabilityScore(
                target=target,
                long_horizon=long,
                short_horizon=short,
                pairs=int(first.size),
                median_revision=float(np.median(revision)),
                median_error=float(np.median(error)),
                median_seed_spread=float(np.median(spread)),
            )
        )
    return found


def _find(
    scores: list[BandScore],
    model: str,
    flag: bool,
    target: ForecastTarget,
    horizon: int,
    split: SplitName,
) -> BandScore | None:
    return next(
        (
            s
            for s in scores
            if s.model == model
            and s.calibrated is flag
            and s.target is target
            and s.horizon == horizon
            and s.split is split
            and s.population is Population.ALL
            and s.period == "final"
        ),
        None,
    )


def approvals(scope: Scope, scores: list[BandScore], model: str, flag: bool) -> list[ApprovalRow]:
    """The rule of the protocol, applied to the final years, per target and horizon."""
    rule = scope.protocol.approval
    nominal = scope.protocol.nominal
    rows: list[ApprovalRow] = []
    for target, horizon in itertools.product(TARGETS, rule.horizons):
        seen = _find(scores, model, flag, target, horizon, SplitName.TEST)
        cold = _find(scores, model, flag, target, horizon, SplitName.COLD_START)
        if seen is None:
            continue
        chosen = scope.select(target, horizon, SplitName.TEST, Population.ALL, "final")
        naive_median = float(np.median(scope.persistence_error(target, horizon, chosen)))
        checks = {
            "enough_examples": seen.examples >= rule.min_examples,
            "coverage_seen": all(
                abs(c - n) <= rule.coverage_tolerance
                for c, n in zip(seen.coverage, nominal, strict=True)
            ),
            "coverage_cold": cold is not None
            and all(
                abs(c - n) <= rule.cold_start_tolerance
                for c, n in zip(cold.coverage, nominal, strict=True)
            ),
            "beats_persistence": seen.vs_persistence_high is not None
            and seen.vs_persistence_high < 0,
            "not_worse_than_best": seen.vs_best is not None and seen.vs_best <= 0,
            "typical_firm": seen.median_ae <= naive_median,
        }
        rows.append(
            ApprovalRow(
                target=target,
                horizon=horizon,
                examples=seen.examples,
                approved=all(checks.values()),
                **checks,
            )
        )
    return rows
