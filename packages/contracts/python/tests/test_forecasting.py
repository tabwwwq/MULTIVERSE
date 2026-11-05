"""Contracts of Stages 15 to 17: dataset, sequences, protocols, benchmark, runs, evaluation."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    EvaluationProtocol,
    ForecastDatasetManifest,
    ForecastProtocol,
    SequenceManifest,
    TrainingRun,
)

SHA = "ab" * 32


def manifest(**changes: Any) -> dict[str, Any]:
    return {
        "dataset_id": f"fds-20261028-{SHA[:12]}",
        "sha256": SHA,
        "universe_id": "sec-1000-20261030",
        "pit_built_at": "2026-10-30T19:00:00Z",
        "data_cutoff": "2026-10-29T03:59:59Z",
        "view": "vintage",
        "first_origin": "2010-03-31",
        "last_origin": "2026-09-30",
        "horizons": [1, 4],
        "targets": ["revenue_growth"],
        "features": ["rev_growth_l1"],
        "rows": 1,
        "companies": 1,
        "contracts_version": "0.13.0",
        "created_at": "2026-10-30T20:00:00Z",
    } | changes


def protocol(**changes: Any) -> dict[str, Any]:
    return {
        "protocol_id": "stage_15_baselines",
        "seed": 1,
        "targets": ["revenue_growth"],
        "horizons": [1, 4],
        "validation_years": [2016, 2019],
        "test_years": [2020],
        "cold_start_share": 0.2,
        "material_revenue": 1e7,
        "winsor_quantile": 0.01,
        "bootstrap_resamples": 1000,
        "grids": {"persistence": [[]]},
    } | changes


def test_the_dataset_is_vintage_and_named_by_its_hash() -> None:
    ForecastDatasetManifest.model_validate_json(json.dumps(manifest()))
    with pytest.raises(ValidationError, match="vintage view"):
        ForecastDatasetManifest.model_validate_json(json.dumps(manifest(view="latest")))
    with pytest.raises(ValidationError, match="named by its SHA-256"):
        ForecastDatasetManifest.model_validate_json(
            json.dumps(manifest(dataset_id="fds-20261028-000000000000"))
        )


def test_the_protocol_keeps_validation_before_the_test_years() -> None:
    ForecastProtocol.model_validate_json(json.dumps(protocol()))
    with pytest.raises(ValidationError, match="before the test years"):
        ForecastProtocol.model_validate_json(json.dumps(protocol(validation_years=[2020])))
    with pytest.raises(ValidationError, match="once each, in order"):
        ForecastProtocol.model_validate_json(json.dumps(protocol(horizons=[4, 1])))


def test_the_benchmark_is_named_by_its_hash() -> None:
    report = {
        "benchmark_id": f"bench-20261028-{SHA[:12]}",
        "sha256": SHA,
        "dataset_id": "fds-20261028-abababababab",
        "dataset_sha256": SHA,
        "protocol_id": "stage_15_baselines",
        "protocol_sha256": SHA,
        "seed": 1,
        "configs": [{"target": "revenue_growth", "model": "persistence"}],
        "scores": [
            {
                "target": "revenue_growth",
                "horizon": 4,
                "split": "test",
                "model": "persistence",
                "examples": 10,
                "companies": 2,
                "mae": 0.1,
                "rmse": 0.2,
                "median_ae": 0.05,
                "firm_weighted_mae": 0.1,
                "revenue_weighted_mae": 0.08,
                "mae_low": 0.09,
                "mae_high": 0.11,
            }
        ],
        "findings": ["revenue_growth h=4: persistence only"],
        "contracts_version": "0.13.0",
        "created_at": "2026-10-30T20:00:00Z",
    }
    BenchmarkReport.model_validate_json(json.dumps(report))
    with pytest.raises(ValidationError, match="named by its SHA-256"):
        BenchmarkReport.model_validate_json(
            json.dumps(report | {"benchmark_id": "bench-20261028-000000000000"})
        )


def sequences(**changes: Any) -> dict[str, Any]:
    return {
        "sequences_id": f"fsq-20261028-{SHA[:12]}",
        "sha256": SHA,
        "dataset_id": f"fds-20261028-{SHA[:12]}",
        "dataset_sha256": SHA,
        "lags": 24,
        "channels": ["rev_growth"],
        "rows": 1,
        "contracts_version": "0.14.0",
        "created_at": "2026-10-31T12:00:00Z",
    } | changes


def test_sequences_are_named_by_their_hash() -> None:
    SequenceManifest.model_validate_json(json.dumps(sequences()))
    with pytest.raises(ValidationError, match="SHA-256"):
        SequenceManifest.model_validate_json(
            json.dumps(sequences(sequences_id="fsq-20261028-000000000000"))
        )


def test_a_protocol_repeats_a_training_at_most_ten_times() -> None:
    assert ForecastProtocol.model_validate_json(json.dumps(protocol())).repeats == 1
    with pytest.raises(ValidationError):
        ForecastProtocol.model_validate_json(json.dumps(protocol(repeats=11)))


def training_run(**changes: Any) -> dict[str, Any]:
    epoch = {
        "epoch": 1,
        "train_loss": 1.2,
        "validation_loss": 1.3,
        "learning_rate": 0.001,
        "seconds": 0.3,
    }
    return {
        "run_id": f"run-20261028-{SHA[:12]}",
        "model": "gru_attention",
        "purpose": "benchmark",
        "dataset_id": f"fds-20261028-{SHA[:12]}",
        "sequences_id": f"fsq-20261028-{SHA[:12]}",
        "fold_year": 2020,
        "seed": 20261030,
        "device": "cuda",
        "torch_version": "2.14.1+cu130",
        "params": [{"name": "hidden", "value": "64"}],
        "train_rows": 10,
        "validation_rows": 2,
        "evaluated_rows": 3,
        "epochs": [epoch],
        "best_epoch": 1,
        "checkpoint_sha256": SHA,
        "created_at": "2026-10-31T12:00:00Z",
    } | changes


def test_the_best_epoch_of_a_training_is_one_it_ran() -> None:
    TrainingRun.model_validate_json(json.dumps(training_run()))
    with pytest.raises(ValidationError, match="best epoch"):
        TrainingRun.model_validate_json(json.dumps(training_run(best_epoch=2)))


def evaluation(**changes: Any) -> dict[str, Any]:
    return {
        "protocol_id": "stage_17_evaluation",
        "base_protocol_id": "stage_16_temporal_large",
        "base_protocol_sha256": SHA,
        "benchmark_id": f"bench-20261028-{SHA[:12]}",
        "seed": 20261030,
        "levels": [0.1, 0.5, 0.9],
        "nominal": [0.8],
        "development_years": [2020],
        "final_years": [2024],
        "repeats": 5,
        "ablation_repeats": 3,
        "ood_z": 4.0,
        "sparse_quarters": 8,
        "dense_quarters": 16,
        "approval": {
            "horizons": [1],
            "min_examples": 300,
            "coverage_tolerance": 0.05,
            "cold_start_tolerance": 0.1,
        },
    } | changes


def test_an_evaluation_decides_on_earlier_years_than_its_verdict() -> None:
    EvaluationProtocol.model_validate_json(json.dumps(evaluation()))
    with pytest.raises(ValidationError, match="before the final years"):
        EvaluationProtocol.model_validate_json(json.dumps(evaluation(development_years=[2024])))


def test_an_evaluation_has_ordered_levels_and_fair_ablations() -> None:
    with pytest.raises(ValidationError, match="in order"):
        EvaluationProtocol.model_validate_json(json.dumps(evaluation(levels=[0.9, 0.5, 0.1])))
    with pytest.raises(ValidationError, match="include the median"):
        EvaluationProtocol.model_validate_json(json.dumps(evaluation(levels=[0.1, 0.9, 0.95])))
    with pytest.raises(ValidationError, match="no more than the full model"):
        EvaluationProtocol.model_validate_json(json.dumps(evaluation(ablation_repeats=6)))
