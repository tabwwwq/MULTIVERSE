"""The worker's rules with an invented trainer: no PyTorch, every ending of a job."""

import itertools
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from multiverse_contracts.forecasting import EpochLog
from multiverse_contracts.jobs import JobEstimate, JobRequest, JobStatus, JobView
from multiverse_jobs.store import JobStore, Limits
from multiverse_worker.runner import (
    Decision,
    DeviceMemoryError,
    RefusedError,
    Session,
    work,
    work_once,
)

SHA = "ab" * 32
ESTIMATE = JobEstimate(seconds=30, vram_mb=500, disk_mb=3, cost_usd=0, basis="invented")
Hook = Callable[[int, JobView], None]


def request(**changes: Any) -> JobRequest:
    values: dict[str, Any] = {
        "idempotency_key": "stage-18-test-run",
        "owner": "owner",
        "model": "gru_attention",
        "dataset_id": f"fds-20261028-{SHA[:12]}",
        "dataset_sha256": SHA,
        "protocol_path": "data/protocols/protocol.json",
        "fold_year": 2026,
        "seed": 1,
        "max_epochs": 5,
        "max_runtime_seconds": 600,
        "spend_limit_usd": 0,
    } | changes
    return JobRequest.model_validate(values)


class Epochs:
    """Runs epochs from where the job stands, as a checkpoint would allow."""

    def __init__(self, hook: Hook | None = None, seconds: float = 1.0) -> None:
        self.hook = hook
        self.seconds = seconds
        self.validated = 0
        self.runs: list[int] = []

    def validate(self, job: JobView) -> None:
        self.validated += 1

    def run(self, job: JobView, session: Session) -> Decision:
        self.runs.append(job.epoch)
        for number in range(job.epoch + 1, job.request.max_epochs + 1):
            if self.hook is not None:
                self.hook(number, job)
            log = EpochLog(
                epoch=number,
                train_loss=1 / number,
                validation_loss=1 / number,
                learning_rate=0.001,
                seconds=self.seconds,
            )
            decision = session.after_epoch(log, number, 1 / number, SHA)
            if number == job.request.max_epochs:
                return "continue"
            if decision != "continue":
                return decision
        return "continue"


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.sqlite", limits=Limits(cloud_spend_usd=100.0))


def queued(store: JobStore, **changes: Any) -> str:
    job, _ = store.submit(request(**changes), ESTIMATE)
    store.approve(job.job_id, "owner")
    return job.job_id


def test_a_job_runs_to_the_end(store: JobStore) -> None:
    job_id = queued(store)
    trainer = Epochs()
    assert work_once(store, trainer, "worker-1", 60)
    job = store.get(job_id)
    assert job.status is JobStatus.COMPLETED
    assert job.progress_percent == 100
    assert job.worker is None
    assert trainer.validated == 1
    assert len(store.detail(job_id).metrics) == 5


def test_stop_ends_at_a_safe_point_and_resume_goes_on(store: JobStore) -> None:
    job_id = queued(store)

    def ask(number: int, _: JobView) -> None:
        if number == 2:
            store.request_stop(job_id)

    trainer = Epochs(ask)
    work_once(store, trainer, "worker-1", 60)
    job = store.get(job_id)
    assert job.status is JobStatus.STOPPED
    assert job.epoch == 2
    assert job.checkpoint_sha256 == SHA
    store.resume(job_id)
    trainer.hook = None
    work_once(store, trainer, "worker-1", 60)
    assert store.get(job_id).status is JobStatus.COMPLETED
    assert trainer.runs == [0, 2]


def test_pause_waits_for_resume(store: JobStore) -> None:
    job_id = queued(store)

    def ask(number: int, _: JobView) -> None:
        if number == 3:
            store.request_pause(job_id)

    work_once(store, Epochs(ask), "worker-1", 60)
    job = store.get(job_id)
    assert job.status is JobStatus.PAUSED
    assert job.epoch == 3
    assert not work_once(store, Epochs(), "worker-1", 60)  # a paused job waits
    store.resume(job_id)
    assert work_once(store, Epochs(), "worker-1", 60)
    assert store.get(job_id).status is JobStatus.COMPLETED


def ticking(step: float) -> Callable[[], float]:
    """A clock that moves ``step`` seconds every time it is read."""
    moments = itertools.count(0.0, step)
    return lambda: next(moments)


def test_the_runtime_budget_stops_a_job_over_all_its_attempts(store: JobStore) -> None:
    job_id = queued(store, max_runtime_seconds=10, max_epochs=50)
    work_once(store, Epochs(), "worker-1", 60, ticking(4.0))
    job = store.get(job_id)
    assert job.status is JobStatus.STOPPED
    assert job.reason is not None
    assert job.reason.startswith("budget: runtime")
    assert job.elapsed_seconds >= 10
    store.resume(job_id)
    work_once(store, Epochs(), "worker-1", 60, ticking(4.0))
    again = store.get(job_id)
    assert again.status is JobStatus.STOPPED  # no new allowance on resume
    assert again.epoch == job.epoch + 1


def test_the_spend_limit_stops_a_paid_job(store: JobStore) -> None:
    job_id = queued(store, rate_usd_per_hour=3600.0, spend_limit_usd=5.0, max_epochs=50)
    work_once(store, Epochs(), "worker-1", 60, ticking(2.0))
    job = store.get(job_id)
    assert job.status is JobStatus.STOPPED
    assert job.reason is not None
    assert job.reason.startswith("budget: spend")
    assert job.spent_usd >= 5


def test_a_loss_that_is_not_a_number_alerts_and_never_retries(store: JobStore) -> None:
    job_id = queued(store)

    def explode(number: int, _: JobView) -> None:
        if number == 2:
            raise FloatingPointError("loss is not finite at epoch 2")

    assert work_once(store, Epochs(explode), "worker-1", 60)
    job = store.get(job_id)
    assert job.status is JobStatus.FAILED
    assert job.alerts
    assert "not finite" in job.alerts[0]
    assert not work_once(store, Epochs(), "worker-1", 60)


def test_out_of_memory_retries_with_half_the_batch(store: JobStore) -> None:
    job_id = queued(store)
    seen: list[int] = []

    def explode(number: int, job: JobView) -> None:
        seen.append(job.batch_size)
        if len(seen) == 1:
            raise DeviceMemoryError("CUDA out of memory")

    trainer = Epochs(explode)
    work_once(store, trainer, "worker-1", 60)
    job = store.get(job_id)
    assert job.status is JobStatus.QUEUED
    assert job.batch_size == 128
    assert job.alerts
    work_once(store, trainer, "worker-1", 60)
    assert store.get(job_id).status is JobStatus.COMPLETED
    assert seen[1] == 128


def test_other_errors_retry_until_the_attempts_end(store: JobStore) -> None:
    job_id = queued(store)

    def explode(*_: object) -> None:
        raise OSError("disk went away")

    trainer = Epochs(explode)
    assert work(store, trainer, "worker-1", 60) == 3
    job = store.get(job_id)
    assert job.status is JobStatus.FAILED
    assert job.attempt == 3
    assert job.reason is not None
    assert "disk went away" in job.reason


def test_a_refused_job_fails_at_once(store: JobStore) -> None:
    job_id = queued(store)

    class Refusing(Epochs):
        def validate(self, job: JobView) -> None:
            raise RefusedError("the dataset does not match the hash of the job")

    work_once(store, Refusing(), "worker-1", 60)
    job = store.get(job_id)
    assert job.status is JobStatus.FAILED
    assert job.attempt == 1
    assert job.alerts


def test_a_worker_that_lost_its_job_writes_nothing_more(store: JobStore) -> None:
    job_id = queued(store)

    def steal(number: int, _: JobView) -> None:
        if number == 2:
            with store._write() as db:
                store._update(db, job_id, worker="worker-2")

    assert work_once(store, Epochs(steal), "worker-1", 60)
    job = store.get(job_id)
    assert job.worker == "worker-2"
    assert job.status is JobStatus.RUNNING
    assert job.epoch == 1


def test_a_worker_exits_when_the_queue_is_empty(store: JobStore) -> None:
    assert work(store, Epochs(), "worker-1", 60) == 0
    queued(store)
    queued(store, idempotency_key="another-test-run")
    assert work(store, Epochs(), "worker-1", 60, max_jobs=1) == 1
    assert work(store, Epochs(), "worker-1", 60) == 1
