"""The temporal model of Stage 16 on invented data. Skipped where PyTorch is not installed.

PyTorch is the optional ``ml`` extra (``uv sync --all-packages --extra ml``); the CI image
installs no extras, so these tests run on machines that train.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from multiverse_contracts.forecasting import (  # noqa: E402
    BenchmarkReport,
    EvaluationProtocol,
    ForecastDatasetManifest,
    ForecastProtocol,
    ForecastTarget,
    ModelConfig,
    Param,
    ScoreRow,
    SplitName,
    TrainingRun,
)
from multiverse_forecast.bands import load_stored  # noqa: E402
from multiverse_forecast.benchmark import Runner  # noqa: E402
from multiverse_forecast.data import LAGS, Dataset, Targets  # noqa: E402
from multiverse_forecast.evaluation import (  # noqa: E402
    DEBT_CHANNEL,
    RND_CHANNEL,
    Variant,
    ablation,
    run_trainings,
    train_variant,
)
from multiverse_forecast.neural import (  # noqa: E402
    HORIZONS,
    QUANTILES,
    TARGETS,
    Arrays,
    CausalConvolutions,
    Config,
    TemporalModel,
    channel_transform,
    load_checkpoint,
    pinball,
    predict,
    quantiles,
    save_checkpoint,
    train,
)
from multiverse_forecast.neural_report import report  # noqa: E402
from multiverse_forecast.neural_run import (  # noqa: E402
    MODEL,
    NeuralBenchmark,
    benchmark,
    run_fold,
)
from multiverse_forecast.probabilistic import (  # noqa: E402
    LEVELS,
    NOMINAL,
    from_target_space,
    to_target_space,
)

LARGE_PROTOCOL = Path(__file__).parents[3] / "data/protocols/stage-16-temporal-large.json"
SMALL = Config(hidden=8, max_epochs=3, patience=2, batch_size=64, threads=1, device="cpu")


def test_quantiles_are_ordered_and_respect_each_target() -> None:
    raw = torch.randn(64, len(TARGETS), len(HORIZONS), len(QUANTILES)) * 10
    q = quantiles(raw)
    assert torch.all(q[..., 0] <= q[..., 1])
    assert torch.all(q[..., 1] <= q[..., 2])
    growth = q[:, TARGETS.index(ForecastTarget.REVENUE_GROWTH)]
    assert torch.all(growth.abs() <= 2)
    assert torch.all(q[:, TARGETS.index(ForecastTarget.DEBT_TO_EBITDA)] >= 0)
    # Smooth transforms: every raw output still receives a gradient (a clamp would not).
    moderate = torch.randn(64, len(TARGETS), len(HORIZONS), len(QUANTILES), requires_grad=True)
    quantiles(moderate).sum().backward()
    assert moderate.grad is not None
    assert torch.all(moderate.grad != 0)


def test_target_spaces_round_trip() -> None:
    y = np.array([-300.0, -0.5, 0.0, 0.12, 4.0])
    for target in TARGETS:
        assert np.allclose(from_target_space(target, to_target_space(target, y)), y)
    margin = to_target_space(ForecastTarget.OPERATING_MARGIN, y)
    assert abs(margin[0]) < 10  # a margin of -300 no longer dominates the loss
    seq = np.array([[[0.5, 3.0, 0.2]]])
    out = channel_transform(np.pad(seq, ((0, 0), (0, 0), (0, 6)), constant_values=0.1))
    assert out[0, 0, 0] == 0.5  # growth unchanged
    assert out[0, 0, 1] == 3.0  # log revenue unchanged
    assert out[0, 0, 2] == pytest.approx(np.arcsinh(2.0))


def test_the_loss_ignores_missing_labels() -> None:
    q = torch.zeros(4, len(TARGETS), len(HORIZONS), len(QUANTILES))
    labels = torch.ones(4, len(TARGETS), len(HORIZONS))
    present = torch.zeros_like(labels)
    present[:, 0, 0] = 1
    base = pinball(q, labels, present)
    labels[:, 1, 1] = 1e6  # a masked label changes nothing
    assert pinball(q, labels, present) == base
    assert torch.isfinite(base)


def arrays(rows: int = 240, seed: int = 0) -> Arrays:
    rng = np.random.default_rng(seed)
    values = rng.normal(size=(rows, 6, 9))
    labels = np.full((rows, len(TARGETS), len(HORIZONS)), np.nan)
    labels[:, 0, :] = np.tanh(values[:, -1, :1].repeat(len(HORIZONS), axis=1))
    labels[rows // 2 :, 1, 1] = values[rows // 2 :, -1, 2]
    return Arrays(values, np.ones_like(values), rng.normal(size=(rows, 5)), labels)


def test_training_is_finite_reproducible_and_checkpointed(tmp_path: Path) -> None:
    data = arrays()
    train_rows, valid_rows = np.arange(0, 180), np.arange(180, 240)
    first = train(data, train_rows, valid_rows, SMALL)
    second = train(data, train_rows, valid_rows, SMALL)
    assert all(np.isfinite([e.train_loss, e.validation_loss]).all() for e in first.epochs)
    assert [e.train_loss for e in first.epochs] == [e.train_loss for e in second.epochs]
    path = tmp_path / "checkpoint.pt"
    save_checkpoint(path, first.model, SMALL, {"mean": [0.0], "std": [1.0]}, first.best_epoch)
    model, config, prep = load_checkpoint(path)
    assert config == SMALL
    assert prep == {"mean": [0.0], "std": [1.0]}
    rows = np.arange(0, 20)
    assert np.allclose(predict(first.model, data, rows, SMALL), predict(model, data, rows, SMALL))


def dataset(firms: int = 24, seed: int = 1) -> tuple[Dataset, np.ndarray]:
    rng = np.random.default_rng(seed)
    origins = [
        np.datetime64(f"{y}-{m:02d}-28", "D") for y in range(2012, 2022) for m in (3, 6, 9, 12)
    ]
    features = (*(c for t in ForecastTarget for c in LAGS[t]), "origin_quarter", "macro_rate")
    n = firms * len(origins)
    x = rng.normal(0.05, 0.05, size=(n, len(features)))
    x[:, features.index("origin_quarter")] = np.tile(np.arange(len(origins)) % 4 + 1, firms)
    ciks = np.repeat([f"{i + 1:010d}" for i in range(firms)], len(origins))
    when = np.tile(np.array(origins), firms)
    targets = {}
    for target in ForecastTarget:
        for horizon in HORIZONS:
            value = x[:, features.index(LAGS[target][0])] * 0.6 + rng.normal(0, 0.02, n)
            if target is ForecastTarget.DEBT_TO_EBITDA:
                value = np.abs(value) * 10
            released = (when + np.timedelta64(91 * horizon + 40, "D")).astype("datetime64[us]")
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
                "first_origin": "2012-03-28",
                "last_origin": "2021-12-28",
                "horizons": list(HORIZONS),
                "targets": [t.value for t in ForecastTarget],
                "features": list(features),
                "rows": n,
                "companies": firms,
                "contracts_version": "0.14.0",
                "created_at": "2022-01-02T00:00:00Z",
            }
        )
    )
    data = Dataset(
        manifest=manifest,
        ciks=ciks,
        origins=when,
        divisions=np.where(np.arange(n) % 2 == 0, "D", "I"),
        rev_ttm=np.full(n, 5e7),
        features=features,
        x=x,
        targets=targets,
    )
    sequences = rng.normal(0.05, 0.05, size=(n, 24, 9))
    sequences[:, :4, :] = np.nan  # short histories are masked, never zero
    return data, sequences


def test_a_fold_trains_scores_and_writes_its_run(tmp_path: Path) -> None:
    data, sequences = dataset()
    protocol = ForecastProtocol.model_validate_json(
        json.dumps(
            {
                "protocol_id": "invented",
                "seed": 5,
                "targets": ["revenue_growth", "operating_margin"],
                "horizons": [1, 4],
                "validation_years": [2017],
                "test_years": [2020],
                "cold_start_share": 0.25,
                "material_revenue": 1e7,
                "winsor_quantile": 0.01,
                "bootstrap_resamples": 100,
                "grids": {"persistence": [[]]},
            }
        )
    )
    result = run_fold(
        data, sequences, "fsq-20220101-" + "cd" * 6, protocol, 2020, SMALL, tmp_path, smoke=True
    )
    run = TrainingRun.model_validate_json((result.folder / "run.json").read_bytes())
    assert run.purpose == "smoke"
    assert run.fold_year == 2020
    assert {p.name for p in result.folder.iterdir()} == {
        "checkpoint.pt",
        "run.json",
        "log.jsonl",
        "plot.svg",
        "scores.json",
    }
    assert len((result.folder / "log.jsonl").read_text(encoding="utf-8").splitlines()) == len(
        run.epochs
    )
    assert "<polyline" in (result.folder / "plot.svg").read_text(encoding="utf-8")
    assert {s.model for s in result.scores} == {MODEL}
    assert {s.split for s in result.scores} <= {SplitName.TEST, SplitName.COLD_START}
    assert all(s.vs_naive is not None for s in result.scores)


def test_the_benchmark_chooses_on_validation_and_scores_each_seed(tmp_path: Path) -> None:
    data, sequences = dataset()
    protocol = ForecastProtocol.model_validate_json(
        json.dumps(
            {
                "protocol_id": "invented",
                "seed": 5,
                "targets": ["revenue_growth"],
                "horizons": [1, 4],
                "validation_years": [2016, 2017],
                "test_years": [2019, 2020],
                "cold_start_share": 0.25,
                "material_revenue": 1e7,
                "winsor_quantile": 0.01,
                "bootstrap_resamples": 100,
                "repeats": 2,
                "grids": {
                    MODEL: [
                        [{"name": "hidden", "value": "4"}],
                        [{"name": "hidden", "value": "8"}],
                    ],
                    "tcn": [[{"name": "hidden", "value": "4"}]],
                },
            }
        )
    )
    result = benchmark(
        data, sequences, "fsq-20220101-" + "cd" * 6, protocol, SMALL, tmp_path, lambda _: None
    )
    assert len(result.choice) == 3
    # GRU: two settings x two validation years, then two test years x two seeds; TCN: one.
    assert len(result.runs) == (2 * 2 + 2 * 2) + (1 * 2 + 2 * 2)
    models = {s.model for s in result.scores}
    assert models == {
        MODEL,
        f"{MODEL}_seed1",
        f"{MODEL}_seed2",
        "tcn",
        "tcn_seed1",
        "tcn_seed2",
    }
    assert {r.model for r in result.runs} == {MODEL, "tcn"}
    test = [s for s in result.scores if s.split is SplitName.TEST and s.horizon == 4]
    assert len({s.examples for s in test if s.population.value == "all"}) == 1
    assert {s.split for s in result.scores} == {
        SplitName.VALIDATION,
        SplitName.TEST,
        SplitName.COLD_START,
    }


def test_the_report_holds_every_setting_of_the_large_grid() -> None:
    # The first large run lost its report here: one finding listed all 20 settings.
    protocol = ForecastProtocol.model_validate_json(LARGE_PROTOCOL.read_bytes())
    data, _ = dataset()
    choice = {
        f"{model}: " + ", ".join(f"{p.name}={p.value}" for p in params): 0.5
        for model, grid in protocol.grids.items()
        for params in grid
    }
    configs = [
        ModelConfig(target=protocol.targets[0], model=model, params=grid[0], validation_mae=0.3)
        for model, grid in protocol.grids.items()
    ]
    score = ScoreRow(
        target=protocol.targets[0],
        horizon=1,
        split=SplitName.VALIDATION,
        model=MODEL,
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
    baselines = BenchmarkReport(
        benchmark_id="bench-20220101-" + "ab" * 6,
        sha256="ab" * 32,
        dataset_id=data.manifest.dataset_id,
        dataset_sha256=data.manifest.sha256,
        protocol_id="invented",
        protocol_sha256="cd" * 32,
        seed=protocol.seed,
        configs=tuple(configs),
        scores=(score,),
        findings=("invented",),
        contracts_version="0.14.0",
        created_at=datetime(2022, 1, 2, tzinfo=UTC),
    )
    result = NeuralBenchmark(configs, [score], [], choice)
    built, _ = report(data, protocol, "cd" * 32, result, baselines)
    assert len(choice) == 20
    assert len(built.findings) == 20 + len(protocol.grids)
    assert all(setting in " ".join(built.findings) for setting in choice)


def test_the_convolutions_never_look_forward() -> None:
    conv = CausalConvolutions(hidden=6, layers=1, dropout=0.0)
    conv.eval()
    x = torch.randn(2, 24, 6)
    changed = x.clone()
    changed[:, 15:] += 5.0  # quarters after the 15th
    before, _ = conv(x)
    after, _ = conv(changed)
    assert torch.allclose(before[:, :15], after[:, :15])
    assert not torch.allclose(before[:, 15:], after[:, 15:])
    tcn = TemporalModel(9, 5, Config(hidden=8, arch="tcn", threads=1, device="cpu"))
    q = tcn(torch.randn(3, 24, 9), torch.ones(3, 24, 9), torch.randn(3, 5))
    assert q.shape == (3, len(TARGETS), len(HORIZONS), len(QUANTILES))


def test_seven_levels_stay_ordered_and_three_keep_their_formula() -> None:
    raw = torch.randn(32, len(TARGETS), len(HORIZONS), len(LEVELS), requires_grad=True) * 5
    q = quantiles(raw)
    assert q.shape == raw.shape
    assert torch.all(q[..., 1:] >= q[..., :-1])
    margin = TARGETS.index(ForecastTarget.OPERATING_MARGIN)
    three = torch.randn(4, len(TARGETS), len(HORIZONS), 3)
    q = quantiles(three)[:, margin]
    median = three[:, margin, :, 1]
    assert torch.allclose(q[..., 0], median - torch.nn.functional.softplus(three[:, margin, :, 0]))
    assert torch.allclose(q[..., 2], median + torch.nn.functional.softplus(three[:, margin, :, 2]))


def test_default_levels_leave_the_config_of_a_stage_16_run_unchanged(tmp_path: Path) -> None:
    assert "levels" not in SMALL.params()
    seven = Config(hidden=8, max_epochs=2, batch_size=64, threads=1, device="cpu", levels=LEVELS)
    assert seven.params()["levels"] == str(LEVELS)
    data = arrays()
    trained = train(data, np.arange(0, 180), np.arange(180, 240), seven)
    rows = np.arange(0, 10)
    path = tmp_path / "checkpoint.pt"
    save_checkpoint(path, trained.model, seven, {}, trained.best_epoch)
    model, config, _ = load_checkpoint(path)
    assert config == seven
    q = predict(model, data, rows, config)
    assert q.shape == (10, len(TARGETS), len(HORIZONS), len(LEVELS))
    spaced = predict(model, data, rows, config, target_space=True)
    margin = TARGETS.index(ForecastTarget.FCF_MARGIN)
    assert np.allclose(q[:, margin], from_target_space(TARGETS[margin], spaced[:, margin]))


def evaluation_protocols() -> tuple[ForecastProtocol, EvaluationProtocol]:
    base = ForecastProtocol.model_validate_json(
        json.dumps(
            {
                "protocol_id": "invented",
                "seed": 5,
                "targets": ["revenue_growth", "fcf_margin"],
                "horizons": [1, 4],
                "validation_years": [2017],
                "test_years": [2019, 2020],
                "cold_start_share": 0.25,
                "material_revenue": 1e7,
                "winsor_quantile": 0.01,
                "bootstrap_resamples": 100,
                "grids": {"gru_attention": [[]]},
            }
        )
    )
    protocol = EvaluationProtocol.model_validate_json(
        json.dumps(
            {
                "protocol_id": "invented_evaluation",
                "base_protocol_id": "invented",
                "base_protocol_sha256": "cd" * 32,
                "benchmark_id": "bench-20220101-" + "ab" * 6,
                "seed": 5,
                "levels": list(LEVELS),
                "nominal": list(NOMINAL),
                "development_years": [2019],
                "final_years": [2020],
                "repeats": 2,
                "ablation_repeats": 1,
                "ablations": ["lags_4"],
                "ood_z": 4.0,
                "sparse_quarters": 8,
                "dense_quarters": 16,
                "approval": {
                    "horizons": [1],
                    "min_examples": 30,
                    "coverage_tolerance": 0.05,
                    "cold_start_tolerance": 0.1,
                },
            }
        )
    )
    return base, protocol


def test_every_ablation_removes_one_input_and_keeps_the_rest() -> None:
    data, sequences = dataset()
    full = Variant("gru_attention_q7", MODEL, (), 5, data, sequences)
    macro = ablation("no_macro", full, 3)
    assert macro.name == "ablation_no_macro"
    assert macro.repeats == 3
    assert np.isnan(macro.dataset.column("macro_rate")).all()
    assert np.array_equal(
        macro.dataset.column("rev_growth_l1"), data.column("rev_growth_l1"), equal_nan=True
    )
    rnd = ablation("no_rnd", full, 3)
    assert np.isnan(rnd.sequences[:, :, RND_CHANNEL]).all()
    assert not np.isnan(rnd.sequences[:, -1, 0]).all()
    debt = ablation("no_debt", full, 3)
    assert np.isnan(debt.sequences[:, :, DEBT_CHANNEL]).all()
    assert np.isnan(debt.dataset.column("debt_to_ebitda_l1")).all()
    short = ablation("lags_4", full, 3)
    assert np.isnan(short.sequences[:, :-4]).all()
    assert np.array_equal(short.sequences[:, -4:], sequences[:, -4:], equal_nan=True)
    assert np.isnan(ablation("no_sequence", full, 3).sequences).all()
    deep = Variant(
        "gru_attention_q7", MODEL, (Param(name="layers", value="1"),), 5, data, sequences
    )
    assert ablation("other_depth", deep, 3).params[0].value == "2"
    with pytest.raises(ValueError, match="unknown ablation"):
        ablation("no_luck", full, 3)


def test_a_variant_stores_quantiles_offsets_and_what_it_remembered(tmp_path: Path) -> None:
    data, sequences = dataset()
    base, protocol = evaluation_protocols()
    runner = Runner(data, base)
    variant = Variant(
        "gru_attention_q7", MODEL, (Param(name="hidden", value="8"),), 2, data, sequences
    )
    found = train_variant(
        runner, variant, base, protocol, "fsq-20220101-" + "cd" * 6, SMALL, tmp_path, lambda _: None
    )
    rows = np.flatnonzero(np.isin(data.years, (2019, 2020)))
    assert found.bands.q.shape == (rows.size, len(TARGETS), len(HORIZONS), len(LEVELS))
    assert np.isfinite(found.bands.q).all()
    assert np.all(np.diff(found.bands.q, axis=-1) >= -1e-5)
    assert found.bands.offsets.shape == (2, len(TARGETS), len(HORIZONS), len(NOMINAL))
    assert np.abs(found.bands.offsets).sum() > 0
    assert found.medians.shape == (2, rows.size, len(TARGETS), len(HORIZONS))
    assert found.partial is not None
    assert not np.allclose(found.partial.q, found.bands.q)  # one seed against two
    assert (found.memory[..., 1] > 0).all(axis=(1, 2, 3)).all()
    assert len(found.runs) == 4
    assert {r.model for r in found.runs} == {"gru_attention_q7"}
    assert all(r.fold_year in (2019, 2020) for r in found.runs)


def test_stopped_trainings_go_on_and_keep_what_is_stored(tmp_path: Path) -> None:
    data, sequences = dataset()
    base, protocol = evaluation_protocols()
    params = (Param(name="hidden", value="8"), Param(name="layers", value="1"))
    benchmark = BenchmarkReport.model_construct(
        configs=(
            ModelConfig(target=ForecastTarget.REVENUE_GROWTH, model=MODEL, params=params),
            ModelConfig(target=ForecastTarget.REVENUE_GROWTH, model="tcn", params=params),
        )
    )
    lines: list[str] = []
    run_trainings(
        data,
        sequences,
        "fsq-20220101-" + "cd" * 6,
        base,
        protocol,
        benchmark,
        SMALL,
        tmp_path,
        lines.append,
    )
    stored = load_stored(tmp_path / "bands")
    assert set(stored.bands) >= {"gru_attention_q7", "tcn_q7", "ablation_lags_4"}
    assert stored.history.size == stored.rows.size
    assert len(stored.checkpoints["gru_attention_q7"]) == 4
    assert any(line.startswith("ablations of") for line in lines)
    assert sum(line.startswith("[") for line in lines) == 10
    assert lines[-1].startswith("[100%] ablation_lags_4")
    first = stored.sha256
    again: list[str] = []
    run_trainings(
        data,
        sequences,
        "fsq-20220101-" + "cd" * 6,
        base,
        protocol,
        benchmark,
        SMALL,
        tmp_path,
        again.append,
    )
    assert not any(line.startswith("[") for line in again)  # nothing trained twice
    assert load_stored(tmp_path / "bands").sha256 == first
