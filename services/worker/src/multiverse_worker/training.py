"""A job as a real training: dataset, fold and resumable loop of ``multiverse_forecast``.

PyTorch is an optional extra, so it is imported only when a job runs. Artifacts of a job
stay in ``<data dir>/jobs/<job id>/``: ``last.pt`` and ``best.pt`` while it lives, and the
usual run folder when it completes.
"""

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from multiverse_contracts.forecasting import ForecastDatasetManifest, ForecastProtocol
from multiverse_contracts.jobs import JobView
from multiverse_worker.runner import Decision, DeviceMemoryError, RefusedError, Session


def code_commit() -> str:
    found = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return found.stdout.strip() or "unknown"


class ForecastTrainer:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def folder(self, job: JobView) -> Path:
        return self.data_dir / "jobs" / job.job_id

    def dataset_folder(self, job: JobView) -> Path:
        return self.data_dir / "forecast" / job.request.dataset_id

    def validate(self, job: JobView) -> None:
        """Dataset hash, sequences, protocol, device and disk, before any training."""
        request = job.request
        folder = self.dataset_folder(job)
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            raise RefusedError(f"no dataset {request.dataset_id}")
        manifest = ForecastDatasetManifest.model_validate_json(manifest_path.read_bytes())
        if manifest.sha256 != request.dataset_sha256:
            raise RefusedError("the dataset does not match the hash of the job")
        if not (folder / "sequences.json").exists():
            raise RefusedError("the dataset has no sequences")
        protocol_path = Path(request.protocol_path)
        if not protocol_path.exists():
            raise RefusedError(f"no protocol {request.protocol_path}")
        protocol = ForecastProtocol.model_validate_json(protocol_path.read_bytes())
        if request.fold_year not in (*protocol.validation_years, *protocol.test_years):
            raise RefusedError(f"{request.fold_year} is not a fold of the protocol")
        try:
            import torch
        except ImportError as error:
            raise RefusedError("PyTorch is not installed: uv sync --extra ml") from error
        if request.device == "cuda" and not torch.cuda.is_available():
            raise RefusedError("the job asks for CUDA and this machine has none")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        free_mb = shutil.disk_usage(self.data_dir).free / 1e6
        if free_mb < job.estimate.disk_mb:
            raise RefusedError(f"{free_mb:.0f} MB free, the job needs {job.estimate.disk_mb} MB")

    def run(self, job: JobView, session: Session) -> Decision:
        import torch

        from multiverse_forecast import resumable
        from multiverse_forecast.benchmark import Runner
        from multiverse_forecast.data import load, load_sequences
        from multiverse_forecast.neural import Config
        from multiverse_forecast.neural_run import fold, save_run, setting

        request = job.request
        dataset_folder = self.dataset_folder(job)
        dataset = load(dataset_folder)
        sequences, sequences_id = load_sequences(dataset_folder, dataset)
        protocol = ForecastProtocol.model_validate_json(Path(request.protocol_path).read_bytes())
        runner = Runner(dataset, protocol)
        current = fold(runner, sequences, request.fold_year, request.seed)
        base = Config(
            device=request.device, max_epochs=request.max_epochs, batch_size=job.batch_size
        )
        config = replace(
            setting(base, request.model, request.params, request.seed),
            max_epochs=request.max_epochs,
        )
        identity = resumable.Identity(
            dataset_sha256=dataset.manifest.sha256,
            sequences_id=sequences_id,
            fold_year=request.fold_year,
            features=dataset.features,
            normalization=current.normalization,
            code_commit=code_commit(),
        )
        folder = self.folder(job)
        try:
            ended = resumable.run(
                current.data,
                current.train_rows,
                current.valid_rows,
                config,
                identity,
                folder,
                session.after_epoch,
            )
        except torch.cuda.OutOfMemoryError as error:
            raise DeviceMemoryError(str(error)) from error
        except resumable.IncompatibleCheckpointError as error:
            raise RefusedError(str(error)) from error
        if ended.trained is None:
            return ended.decision
        run, run_folder = save_run(
            runner,
            sequences_id,
            current,
            ended.trained,
            config,
            folder / "run",
            smoke=False,
            max_train_rows=None,
            evaluated=0,
            model=request.model,
        )
        record = json.loads((run_folder / "run.json").read_text(encoding="utf-8"))
        record["purpose"] = "job"
        (run_folder / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        session.reason = f"finished after {len(run.epochs)} epochs, best {run.best_epoch}"
        resumable.clean(folder)
        digest = hashlib.sha256((run_folder / "checkpoint.pt").read_bytes()).hexdigest()
        session.store.log(job.job_id, "info", f"run {run.run_id}, checkpoint {digest[:12]}")
        return "continue"
