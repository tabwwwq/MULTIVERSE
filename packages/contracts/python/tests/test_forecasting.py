"""Contracts of Stage 15: the dataset manifest, the locked protocol, the benchmark report."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    ForecastDatasetManifest,
    ForecastProtocol,
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
