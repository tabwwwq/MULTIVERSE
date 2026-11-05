"""What a job must bring before it may train: refusals that need no PyTorch."""

import json
from pathlib import Path

import pytest

from multiverse_contracts.jobs import JobEstimate, JobRequest, JobStatus, JobView
from multiverse_worker.runner import RefusedError
from multiverse_worker.training import ForecastTrainer

SHA = "ab" * 32
DATASET = f"fds-20261028-{SHA[:12]}"
MANIFEST = {
    "dataset_id": DATASET,
    "sha256": SHA,
    "universe_id": "invented",
    "pit_built_at": "2026-10-28T00:00:00Z",
    "data_cutoff": "2026-10-28T05:00:00Z",
    "view": "vintage",
    "first_origin": "2010-03-31",
    "last_origin": "2026-09-30",
    "horizons": [1],
    "targets": ["revenue_growth"],
    "features": ["rev_growth_l1"],
    "rows": 1,
    "companies": 1,
    "contracts_version": "0.16.0",
    "created_at": "2026-10-28T00:00:00Z",
}
PROTOCOL = {
    "protocol_id": "invented",
    "seed": 1,
    "targets": ["revenue_growth"],
    "horizons": [1],
    "validation_years": [2016],
    "test_years": [2020],
    "cold_start_share": 0.2,
    "material_revenue": 1e7,
    "winsor_quantile": 0.01,
    "bootstrap_resamples": 100,
    "grids": {"gru_attention": [[]]},
}


def job(protocol: Path, **changes: object) -> JobView:
    request = JobRequest.model_validate(
        {
            "idempotency_key": "stage-18-test-run",
            "owner": "owner",
            "model": "gru_attention",
            "dataset_id": DATASET,
            "dataset_sha256": SHA,
            "protocol_path": str(protocol),
            "fold_year": 2020,
            "seed": 1,
            "max_epochs": 5,
            "max_runtime_seconds": 60,
            "spend_limit_usd": 0,
        }
        | changes
    )
    return JobView.model_validate(
        {
            "job_id": "job-0123456789ab",
            "request": request,
            "estimate": JobEstimate(seconds=1, vram_mb=1, disk_mb=1, cost_usd=0, basis="invented"),
            "status": JobStatus.VALIDATING,
            "attempt": 1,
            "max_attempts": 3,
            "epoch": 0,
            "batch_size": 256,
            "progress_percent": 0,
            "elapsed_seconds": 0,
            "spent_usd": 0,
            "created_at": "2026-11-05T20:00:00+00:00",
            "updated_at": "2026-11-05T20:00:00+00:00",
        },
        strict=False,
    )


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "forecast" / DATASET
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (folder / "sequences.json").write_text("{}", encoding="utf-8")
    (tmp_path / "protocol.json").write_text(json.dumps(PROTOCOL), encoding="utf-8")
    return tmp_path


def test_a_job_needs_its_dataset_with_its_hash(data_dir: Path) -> None:
    protocol = data_dir / "protocol.json"
    trainer = ForecastTrainer(data_dir)
    with pytest.raises(RefusedError, match="no dataset"):
        trainer.validate(job(protocol, dataset_id="fds-20261028-" + "cd" * 6))
    with pytest.raises(RefusedError, match="hash of the job"):
        trainer.validate(job(protocol, dataset_sha256="cd" * 32))


def test_a_job_needs_sequences_a_protocol_and_a_fold_of_it(data_dir: Path) -> None:
    protocol = data_dir / "protocol.json"
    trainer = ForecastTrainer(data_dir)
    with pytest.raises(RefusedError, match="no protocol"):
        trainer.validate(job(data_dir / "missing.json"))
    with pytest.raises(RefusedError, match="not a fold"):
        trainer.validate(job(protocol, fold_year=2021))
    (data_dir / "forecast" / DATASET / "sequences.json").unlink()
    with pytest.raises(RefusedError, match="no sequences"):
        trainer.validate(job(protocol))
