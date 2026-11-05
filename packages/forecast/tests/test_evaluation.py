"""Stage 17 on invented data: scores, calibration, baseline bands, the package. No PyTorch."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    EvaluationPackage,
    EvaluationProtocol,
    ForecastDatasetManifest,
    ForecastProtocol,
    ForecastTarget,
    ModelConfig,
    Param,
    ScoreRow,
    SplitName,
)
from multiverse_forecast import evaluation_report
from multiverse_forecast.bands import (
    HORIZONS,
    PARTIAL,
    TARGETS,
    Bands,
    Stored,
    baseline_bands,
    load_stored,
    residual_band,
    save_arrays,
)
from multiverse_forecast.benchmark import Runner, boundary, watch_rows
from multiverse_forecast.data import LAGS, Dataset, Targets
from multiverse_forecast.evaluation_scores import (
    Entry,
    approvals,
    band_scores,
    calibrated,
    choose_primary,
    entries_of,
    scope_of,
)
from multiverse_forecast.probabilistic import (
    LEVELS,
    NOMINAL,
    conformal_offset,
    conformalize,
    covered,
    firm_interval,
    from_target_space,
    interval_columns,
    pinball_rows,
    ratio_interval,
    reliability,
    to_target_space,
    widths,
    wis_rows,
)

GRU = "gru_attention_q7"
TCN = "tcn_q7"
NORMAL_Z = np.array([-1.645, -1.2816, -0.6745, 0.0, 0.6745, 1.2816, 1.645])


def normal_quantiles(rows: int, scale: float = 1.0) -> np.ndarray:
    return np.tile(NORMAL_Z * scale, (rows, 1))


def test_pinball_at_the_median_is_half_the_absolute_error() -> None:
    q = np.array([[1.0]])
    assert pinball_rows(q, np.array([3.0]), (0.5,))[0] == pytest.approx(1.0)
    # A forecast too low costs more at a high level than at a low one.
    high = pinball_rows(q, np.array([3.0]), (0.9,))[0]
    low = pinball_rows(q, np.array([3.0]), (0.1,))[0]
    assert high == pytest.approx(1.8)
    assert low == pytest.approx(0.2)


def test_the_weighted_interval_score_follows_its_definition() -> None:
    q = np.array([[0.0, 1.0, 2.0]])
    levels = (0.1, 0.5, 0.9)
    inside = wis_rows(q, np.array([1.0]), levels)[0]
    assert inside == pytest.approx((0.2 / 2) * 2.0 / 1.5)
    outside = wis_rows(q, np.array([4.0]), levels)[0]
    score = 2.0 + (2 / 0.2) * 2.0
    assert outside == pytest.approx((0.5 * 3.0 + 0.2 / 2 * score) / 1.5)
    with pytest.raises(ValueError, match="median"):
        wis_rows(np.zeros((1, 2)), np.zeros(1), (0.25, 0.75))


def test_a_true_distribution_covers_what_it_says() -> None:
    rng = np.random.default_rng(3)
    y = rng.normal(size=200_000)
    q = normal_quantiles(y.size)
    assert covered(q, y, 0.8).mean() == pytest.approx(0.8, abs=0.005)
    assert covered(q, y, 0.5).mean() == pytest.approx(0.5, abs=0.005)
    assert reliability(q, y) == pytest.approx(np.array(LEVELS), abs=0.005)
    assert widths(q, 0.8)[0] == pytest.approx(2 * 1.2816)
    assert interval_columns(0.9) == (0, 6)
    with pytest.raises(ValueError, match="no levels"):
        interval_columns(0.7)
    # Proper: the truth scores better than a band too narrow or too wide.
    truth = pinball_rows(q, y).mean()
    assert truth < pinball_rows(normal_quantiles(y.size, 0.5), y).mean()
    assert truth < pinball_rows(normal_quantiles(y.size, 2.0), y).mean()


def test_conformal_offsets_repair_a_narrow_band_and_keep_it_ordered() -> None:
    rng = np.random.default_rng(4)
    calibration, new = rng.normal(size=5000), rng.normal(size=50_000)
    narrow = normal_quantiles(calibration.size, 0.5)
    offsets = {n: conformal_offset(narrow, calibration, n) for n in NOMINAL}
    assert all(v > 0 for v in offsets.values())
    fixed = conformalize(normal_quantiles(new.size, 0.5), offsets)
    assert np.all(np.diff(fixed, axis=1) >= 0)
    assert fixed[:, 3] == pytest.approx(0.0)  # the median stays
    for nominal in NOMINAL:
        assert covered(fixed, new, nominal).mean() == pytest.approx(nominal, abs=0.02)
    wide = normal_quantiles(calibration.size, 3.0)
    assert conformal_offset(wide, calibration, 0.8) < 0  # too wide: it narrows


def test_a_bootstrap_over_firms_sees_how_few_firms_there_are() -> None:
    one_firm = np.array(["a"] * 100 + ["b"] * 100)
    many = np.array([f"f{i}" for i in range(200)])
    values = np.r_[np.zeros(100), np.ones(100)]
    low, high = firm_interval(one_firm, values, 500, 1)
    wide = high - low
    low, high = firm_interval(many, values, 500, 1)
    assert wide > 2 * (high - low)
    change, low, high = ratio_interval(many, values + 1, values + 2, 500, 1)
    assert low < change < high
    assert change == pytest.approx(1.5 / 2.5 - 1)


def test_target_spaces_keep_quantiles_in_order() -> None:
    values = np.array([-300.0, -0.5, 0.0, 0.12, 4.0])
    for target in TARGETS:
        if target is ForecastTarget.DEBT_TO_EBITDA:
            continue
        spaced = to_target_space(target, values)
        assert np.all(np.diff(spaced) > 0)
        assert from_target_space(target, spaced) == pytest.approx(values)


def world(firms: int = 40, seed: int = 2) -> Dataset:
    """Invented firms with mean-reverting ratios, 2012-2021, released with a delay."""
    rng = np.random.default_rng(seed)
    origins = [
        np.datetime64(f"{y}-{m}", "D")
        for y in range(2012, 2022)
        for m in ("03-31", "06-30", "09-30", "12-31")
    ]
    features = (*(c for t in ForecastTarget for c in LAGS[t]), "origin_quarter", "macro_rate")
    n = firms * len(origins)
    x = rng.normal(0.1, 0.05, size=(n, len(features)))
    x[:, features.index("origin_quarter")] = np.tile(np.arange(len(origins)) % 4 + 1, firms)
    when = np.tile(np.array(origins), firms)
    targets = {}
    for target in ForecastTarget:
        for horizon in HORIZONS:
            value = 0.6 * x[:, features.index(LAGS[target][0])] + rng.normal(0, 0.03, n)
            if target is ForecastTarget.DEBT_TO_EBITDA:
                value = np.abs(value) * 5
            released = (when + np.timedelta64(91 * horizon + 40, "D")).astype("datetime64[us]")
            late = released > np.datetime64("2022-01-01T05:00:00", "us")
            value[late] = np.nan
            targets[(target, horizon)] = Targets(value, np.zeros(n, dtype=bool), released)
    manifest = ForecastDatasetManifest.model_validate_json(
        json.dumps(
            {
                "dataset_id": "fds-20220101-" + "ab" * 6,
                "sha256": "ab" * 32,
                "universe_id": "invented",
                "pit_built_at": "2022-01-02T00:00:00Z",
                "data_cutoff": "2022-01-01T05:00:00Z",
                "view": "vintage",
                "first_origin": "2012-03-31",
                "last_origin": "2021-12-31",
                "horizons": list(HORIZONS),
                "targets": [t.value for t in ForecastTarget],
                "features": list(features),
                "rows": n,
                "companies": firms,
                "contracts_version": "0.15.0",
                "created_at": "2022-01-02T00:00:00Z",
            }
        )
    )
    return Dataset(
        manifest=manifest,
        ciks=np.repeat([f"{i + 1:010d}" for i in range(firms)], len(origins)),
        origins=when,
        divisions=np.where(np.arange(n) % 2 == 0, "D", "I"),
        rev_ttm=np.full(n, 5e7),
        features=features,
        x=x,
        targets=targets,
    )


def base_protocol() -> ForecastProtocol:
    return ForecastProtocol.model_validate_json(
        json.dumps(
            {
                "protocol_id": "invented",
                "seed": 5,
                "targets": [t.value for t in ForecastTarget],
                "horizons": list(HORIZONS),
                "validation_years": [2016],
                "test_years": [2018, 2019, 2020, 2021],
                "cold_start_share": 0.25,
                "material_revenue": 1e7,
                "winsor_quantile": 0.01,
                "bootstrap_resamples": 100,
                "repeats": 2,
                "grids": {"persistence": [[]]},
            }
        )
    )


def evaluation_protocol() -> EvaluationProtocol:
    return EvaluationProtocol.model_validate_json(
        json.dumps(
            {
                "protocol_id": "invented_evaluation",
                "base_protocol_id": "invented",
                "base_protocol_sha256": "cd" * 32,
                "benchmark_id": "bench-20220101-" + "ab" * 6,
                "seed": 5,
                "levels": list(LEVELS),
                "nominal": list(NOMINAL),
                "development_years": [2018, 2019],
                "final_years": [2020, 2021],
                "repeats": 2,
                "ablation_repeats": 1,
                "ablations": ["no_macro"],
                "ood_z": 4.0,
                "sparse_quarters": 8,
                "dense_quarters": 16,
                "approval": {
                    "horizons": [1, 4],
                    "min_examples": 30,
                    "coverage_tolerance": 0.05,
                    "cold_start_tolerance": 0.1,
                },
            }
        )
    )


def stage15(dataset: Dataset) -> BenchmarkReport:
    gbm = (
        Param(name="max_depth", value="2"),
        Param(name="learning_rate", value="0.1"),
        Param(name="max_iter", value="5"),
        Param(name="min_samples_leaf", value="20"),
    )
    net = (Param(name="alpha", value="0.01"), Param(name="l1_ratio", value="0.5"))
    configs = [ModelConfig(target=t, model="gbm", params=gbm) for t in ForecastTarget]
    configs += [ModelConfig(target=t, model="elastic_net", params=net) for t in ForecastTarget]
    score = ScoreRow(
        target=ForecastTarget.REVENUE_GROWTH,
        horizon=1,
        split=SplitName.TEST,
        model="gbm",
        examples=1,
        companies=1,
        mae=0.3,
        rmse=0.3,
        median_ae=0.3,
        firm_weighted_mae=0.3,
        revenue_weighted_mae=0.3,
        mae_low=0.2,
        mae_high=0.4,
    )
    return BenchmarkReport(
        benchmark_id="bench-20220101-" + "ab" * 6,
        sha256="ab" * 32,
        dataset_id=dataset.manifest.dataset_id,
        dataset_sha256=dataset.manifest.sha256,
        protocol_id="invented",
        protocol_sha256="cd" * 32,
        seed=5,
        configs=tuple(configs),
        scores=(score,),
        findings=("invented",),
        contracts_version="0.15.0",
        created_at=datetime(2022, 1, 2, tzinfo=UTC),
    )


def test_a_residual_band_is_the_point_plus_its_errors() -> None:
    y = np.arange(101.0)
    point = np.zeros(101)
    point[0] = np.nan  # a row without a forecast does not count
    band = residual_band(point, y, np.array([10.0]), (0.0, 0.5, 1.0))
    assert band[0] == pytest.approx([11.0, 60.5, 110.0])


def test_baseline_bands_are_ordered_and_calibrate_on_watch_firms() -> None:
    dataset = world()
    base = base_protocol()
    runner = Runner(dataset, base)
    rows, bands = baseline_bands(
        runner, stage15(dataset), evaluation_protocol(), base.test_years, lambda _: None
    )
    assert set(bands) == {"persistence", "elastic_net", "gbm", "gbm_quantile"}
    assert np.array_equal(rows, np.flatnonzero(np.isin(dataset.years, base.test_years)))
    known = ~np.isnan(bands["gbm_quantile"].q)
    assert known.any()
    q = bands["gbm_quantile"].q[known.all(axis=-1)]
    assert np.all(np.diff(q, axis=-1) >= 0)
    # Calibration rows are watch firms: rows of training firms, never cold starts.
    watched = watch_rows(runner)
    assert watched.any()
    assert not (watched & runner.cold).any()
    target = dataset.targets[(ForecastTarget.REVENUE_GROWTH, 4)]
    usable = watched & ~np.isnan(target.value) & (target.released <= boundary(2018))
    assert (dataset.years[usable] < 2018).all()


def invented_stored(dataset: Dataset, narrow: float = 0.5) -> Stored:
    """Bands of two invented networks and the baselines: one is simply better."""
    base = base_protocol()
    protocol = evaluation_protocol()
    runner = Runner(dataset, base)
    rows, bands = baseline_bands(
        runner, stage15(dataset), protocol, base.test_years, lambda _: None
    )
    good = bands["gbm_quantile"]
    worse = Bands((good.q * 1.5 + 0.2).astype(np.float32), good.offsets.copy())
    median = good.q[..., 3:4]
    tight = Bands((median + narrow * (good.q - median)).astype(np.float32), good.offsets.copy())
    bands |= {GRU: tight, TCN: worse, GRU + PARTIAL: tight, "ablation_no_macro": worse}
    medians = np.stack([good.q[..., 3], good.q[..., 3] + 0.01])
    memory = np.ones((len(base.test_years), 2, len(TARGETS), len(HORIZONS), 2))
    return Stored(
        rows=rows,
        bands=bands,
        history=np.full(rows.size, 20.0),
        outside=np.arange(rows.size) % 10 == 0,
        medians={GRU: medians, TCN: medians},
        memory={GRU: memory, TCN: memory},
        checkpoints={GRU: ["ab" * 32], TCN: ["cd" * 32]},
        sha256="ef" * 32,
    )


@pytest.fixture(scope="module")
def invented() -> tuple[Dataset, Stored]:
    dataset = world()
    return dataset, invented_stored(dataset)


def test_every_band_is_scored_on_the_same_rows(invented: tuple[Dataset, Stored]) -> None:
    dataset, stored = invented
    base, protocol = base_protocol(), evaluation_protocol()
    scope = scope_of(dataset, base, protocol, stored)
    entries = entries_of(stored, scope, base)
    scores = band_scores(scope, entries)
    assert {(s.model, s.calibrated) for s in scores} == set(entries)
    cells: dict[tuple[object, ...], set[int]] = {}
    for s in scores:
        key = (s.target, s.horizon, s.split, s.population, s.period)
        cells.setdefault(key, set()).add(s.examples)
    assert all(len(v) == 1 for v in cells.values())
    assert {s.period for s in scores} == {"development", "final", "all"}
    first = next(s for s in scores if s.model == GRU)
    assert first.vs_best is not None
    assert first.best_baseline is not None
    assert all(s.vs_best is None for s in scores if s.model == "persistence")


def test_the_chosen_model_comes_from_the_development_years_only(
    invented: tuple[Dataset, Stored],
) -> None:
    dataset, stored = invented
    base, protocol = base_protocol(), evaluation_protocol()
    scope = scope_of(dataset, base, protocol, stored)
    entries = entries_of(stored, scope, base)
    assert choose_primary(scope, entries)[0] == GRU
    # Ruin the final years of the better network: nothing changes.
    final = np.isin(scope.years, protocol.final_years)
    ruined = entries[(GRU, False)].q.copy()
    ruined[final] += 100
    changed = dict(entries)
    changed[(GRU, False)] = Entry(GRU, False, ruined)
    changed[(GRU, True)] = Entry(GRU, True, ruined)
    assert choose_primary(scope, changed)[0] == GRU


def test_calibration_uses_the_offsets_of_each_fold(invented: tuple[Dataset, Stored]) -> None:
    dataset, stored = invented
    base, protocol = base_protocol(), evaluation_protocol()
    scope = scope_of(dataset, base, protocol, stored)
    band = stored.bands[GRU]
    moved = Bands(band.q, np.zeros_like(band.offsets))
    moved.offsets[1] = 1.0  # only the second test year moves
    fixed = calibrated(moved, scope.years, base.test_years, protocol)
    known = ~np.isnan(band.q).any(axis=-1)
    same = (scope.years == 2018)[:, None, None] & known
    other = (scope.years == 2019)[:, None, None] & known
    assert np.allclose(fixed[same], band.q[same].astype(np.float64))
    low, high = interval_columns(0.9)
    span = fixed[..., high] - fixed[..., low]
    before = band.q[..., high].astype(np.float64) - band.q[..., low]
    assert (span[other] - before[other]).min() > 1.9


def test_approval_needs_every_check(invented: tuple[Dataset, Stored]) -> None:
    dataset, stored = invented
    base, protocol = base_protocol(), evaluation_protocol()
    scope = scope_of(dataset, base, protocol, stored)
    scores = band_scores(scope, entries_of(stored, scope, base))
    rows = approvals(scope, scores, GRU, False)
    assert rows
    assert {r.horizon for r in rows} <= set(protocol.approval.horizons)
    for row in rows:
        checks = (
            row.enough_examples,
            row.coverage_seen,
            row.coverage_cold,
            row.beats_persistence,
            row.not_worse_than_best,
            row.typical_firm,
        )
        assert row.approved == all(checks)
    # A band half as wide as the true spread never covers what it says.
    assert not any(r.coverage_seen for r in rows)


def test_the_package_keeps_failures_and_is_named_by_its_hash(
    invented: tuple[Dataset, Stored], tmp_path: Path
) -> None:
    dataset, stored = invented
    base, protocol = base_protocol(), evaluation_protocol()
    measured = evaluation_report.measure(dataset, base, protocol, stored)
    benchmark = stage15(dataset)
    package = evaluation_report.build(
        dataset, "fsq-20220101-" + "cd" * 6, protocol, "cd" * 32, benchmark, measured, stored
    )
    again = evaluation_report.build(
        dataset, "fsq-20220101-" + "cd" * 6, protocol, "cd" * 32, benchmark, measured, stored
    )
    assert package.sha256 == again.sha256
    assert package.model_id.startswith("model-20220101-")
    assert package.primary_model == GRU
    assert package.failures
    assert package.ablations
    assert package.memorization
    assert package.stability
    assert package.companies
    assert {s.kind for s in package.slices} == {"year", "division", "history", "distribution"}
    figures = tmp_path / "figures"
    folder = evaluation_report.write(package, protocol, tmp_path, figures)
    stored_package = EvaluationPackage.model_validate_json((folder / "package.json").read_bytes())
    assert stored_package.evaluation_id == package.evaluation_id
    assert "## Failures" in (folder / "report.md").read_text(encoding="utf-8")
    assert "<!doctype html>" in (folder / "report.html").read_text(encoding="utf-8")
    names = {p.name for p in figures.iterdir()}
    assert names == {
        "reliability.svg",
        "coverage-by-year.svg",
        "against-persistence.svg",
        "ablations.svg",
    }
    assert all("<circle" in (figures / n).read_text(encoding="utf-8") for n in names)


def test_stored_bands_come_back_and_must_share_their_rows(tmp_path: Path) -> None:
    rows = np.arange(4)
    band = Bands.empty(4, 1, len(LEVELS), len(NOMINAL))
    save_arrays(
        tmp_path,
        GRU,
        {
            "rows": rows,
            "q": band.q,
            "offsets": band.offsets,
            "partial": band.q,
            "medians": np.zeros((1, 4, 5, 5)),
            "memory": np.zeros((1, 2, 5, 5, 2)),
            "checkpoints": np.array(["ab" * 32]),
        },
    )
    save_arrays(tmp_path, "conditions", {"history": np.ones(4), "outside": np.zeros(4, dtype=bool)})
    stored = load_stored(tmp_path)
    assert set(stored.bands) == {GRU, GRU + PARTIAL}
    assert stored.checkpoints[GRU] == ["ab" * 32]
    assert stored.history.size == 4
    first = stored.sha256
    assert load_stored(tmp_path).sha256 == first
    save_arrays(tmp_path, TCN, {"rows": rows + 1, "q": band.q, "offsets": band.offsets})
    with pytest.raises(ValueError, match="other rows"):
        load_stored(tmp_path)
