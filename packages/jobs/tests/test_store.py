"""The durable queue: idempotency, leases, requests, budgets at the door, clean logs."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from multiverse_contracts.forecasting import EpochLog
from multiverse_contracts.jobs import JobEstimate, JobRequest, JobStatus
from multiverse_jobs.estimate import MAX_RUNTIME_SECONDS, estimate, refusals
from multiverse_jobs.redact import redact
from multiverse_jobs.store import JobError, JobStore, LeaseLostError, job_id_of

SHA = "ab" * 32


def request(**changes: Any) -> JobRequest:
    values: dict[str, Any] = {
        "idempotency_key": "stage-18-test-run",
        "owner": "owner",
        "model": "gru_attention",
        "dataset_id": f"fds-20261028-{SHA[:12]}",
        "dataset_sha256": SHA,
        "protocol_path": "data/protocols/stage-16-temporal-large.json",
        "fold_year": 2026,
        "seed": 20261030,
        "max_epochs": 10,
        "max_runtime_seconds": 600,
        "spend_limit_usd": 0,
    } | changes
    return JobRequest.model_validate(values)


ESTIMATE = JobEstimate(seconds=30, vram_mb=500, disk_mb=3, cost_usd=0, basis="invented")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 5, 20, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def move(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> JobStore:
    return JobStore(tmp_path / "jobs.sqlite", clock)


def approved(store: JobStore, **changes: Any) -> str:
    job, _ = store.submit(request(**changes), ESTIMATE)
    store.approve(job.job_id, "owner")
    return job.job_id


def epoch(number: int) -> EpochLog:
    return EpochLog(
        epoch=number, train_loss=1.0, validation_loss=0.9, learning_rate=0.001, seconds=1.0
    )


def test_a_repeated_submit_returns_the_same_job(store: JobStore) -> None:
    first, created = store.submit(request(), ESTIMATE)
    second, again = store.submit(request(), ESTIMATE)
    assert created
    assert not again
    assert first.job_id == second.job_id == job_id_of("stage-18-test-run")
    assert len(store.jobs()) == 1
    with pytest.raises(JobError, match="another request"):
        store.submit(request(max_epochs=11), ESTIMATE)


def test_nothing_runs_before_its_estimate_is_approved(store: JobStore) -> None:
    job, _ = store.submit(request(), ESTIMATE)
    assert job.status is JobStatus.QUEUED
    assert store.lease("worker-1", 1, 60) is None
    store.approve(job.job_id, "owner")
    taken = store.lease("worker-1", 1, 60)
    assert taken is not None
    assert taken.status is JobStatus.VALIDATING
    assert taken.approved_by == "owner"
    assert taken.attempt == 1


def test_a_job_has_one_worker_and_a_silent_worker_loses_it(store: JobStore, clock: Clock) -> None:
    job_id = approved(store)
    assert store.lease("worker-1", 1, 60) is not None
    assert store.lease("worker-2", 2, 60) is None
    clock.move(30)
    store.heartbeat(job_id, "worker-1", 60)
    clock.move(50)
    assert store.lease("worker-2", 2, 60) is None  # the heartbeat kept the lease
    clock.move(11)
    taken = store.lease("worker-2", 2, 60)
    assert taken is not None
    assert taken.worker == "worker-2"
    assert taken.attempt == 2
    with pytest.raises(LeaseLostError):
        store.heartbeat(job_id, "worker-1", 60)
    with pytest.raises(LeaseLostError):
        store.epoch_done(job_id, "worker-1", epoch(1), 1, 0.9, 1.0, None)
    assert any("stopped answering" in line.message for line in store.logs(job_id))


def test_a_job_that_kills_its_workers_gives_up(store: JobStore, clock: Clock) -> None:
    job_id = approved(store)
    for attempt in range(3):
        assert store.lease(f"worker-{attempt}", attempt, 60) is not None
        clock.move(61)
    assert store.lease("worker-last", 9, 60) is None
    job = store.get(job_id)
    assert job.status is JobStatus.FAILED
    assert job.reason == "gave up after 3 attempts"


def test_state_survives_every_connection(tmp_path: Path, clock: Clock) -> None:
    path = tmp_path / "jobs.sqlite"
    store = JobStore(path, clock)
    job_id = approved(store)
    store.lease("worker-1", 1, 60)
    store.started(job_id, "worker-1")
    store.epoch_done(job_id, "worker-1", epoch(3), 2, 0.8, 12.0, SHA)
    job = JobStore(path, clock).detail(job_id)
    assert job.job.status is JobStatus.RUNNING
    assert job.job.epoch == 3
    assert job.job.progress_percent == pytest.approx(30)
    assert job.job.best_epoch == 2
    assert job.job.checkpoint_sha256 == SHA
    assert [m.epoch for m in job.metrics] == [3]


def test_stop_and_pause_wait_for_the_worker(store: JobStore) -> None:
    job_id = approved(store)
    store.lease("worker-1", 1, 60)
    store.started(job_id, "worker-1")
    assert store.heartbeat(job_id, "worker-1", 60) is None
    assert store.request_pause(job_id).status is JobStatus.PAUSE_REQUESTED
    assert store.heartbeat(job_id, "worker-1", 60) == "pause"
    paused = store.finish(job_id, "worker-1", JobStatus.PAUSED, "pause at a safe point")
    assert paused.worker is None
    assert store.resume(job_id).status is JobStatus.QUEUED
    taken = store.lease("worker-1", 1, 60)
    assert taken is not None
    store.started(job_id, "worker-1")
    assert store.request_stop(job_id).status is JobStatus.STOP_REQUESTED
    assert store.heartbeat(job_id, "worker-1", 60) == "stop"
    store.finish(job_id, "worker-1", JobStatus.STOPPED, "stop at a safe point")
    with pytest.raises(JobError, match="cannot pause"):
        store.request_pause(job_id)


def test_a_request_during_validation_is_kept(store: JobStore) -> None:
    job_id = approved(store)
    store.lease("worker-1", 1, 60)
    assert store.request_stop(job_id).status is JobStatus.VALIDATING
    assert store.started(job_id, "worker-1").status is JobStatus.STOP_REQUESTED


def test_a_waiting_job_stops_at_once_and_a_finished_one_never_moves(store: JobStore) -> None:
    job, _ = store.submit(request(), ESTIMATE)
    assert store.request_stop(job.job_id).status is JobStatus.STOPPED
    job_id = approved(store, idempotency_key="another-test-run")
    store.lease("worker-1", 1, 60)
    store.started(job_id, "worker-1")
    done = store.finish(job_id, "worker-1", JobStatus.COMPLETED, "finished")
    assert done.progress_percent == 100
    with pytest.raises(JobError):
        store.resume(job_id)


def test_a_resumed_job_keeps_the_budget_it_used(store: JobStore) -> None:
    job_id = approved(store, rate_usd_per_hour=3.6, spend_limit_usd=1.0)
    store.lease("worker-1", 1, 60)
    store.started(job_id, "worker-1")
    store.epoch_done(job_id, "worker-1", epoch(1), 1, 0.9, 100.0, None)
    store.finish(job_id, "worker-1", JobStatus.STOPPED, "budget")
    job = store.resume(job_id)
    assert job.elapsed_seconds == 100
    assert job.spent_usd == pytest.approx(0.1)
    assert job.attempt == 1


def test_retries_end_and_a_smaller_batch_is_kept(store: JobStore) -> None:
    job_id = approved(store)
    store.lease("worker-1", 1, 60)
    store.started(job_id, "worker-1")
    job = store.retry(job_id, "worker-1", "out of memory", batch_size=128)
    assert job.status is JobStatus.QUEUED
    assert job.batch_size == 128
    for _ in range(2):
        store.lease("worker-1", 1, 60)
        store.started(job_id, "worker-1")
        job = store.retry(job_id, "worker-1", "boom")
    assert job.status is JobStatus.FAILED
    assert store.resume(job_id).attempt == 0  # the owner may try again


def test_logs_read_from_a_cursor_and_hold_no_secrets(store: JobStore) -> None:
    job_id = approved(store)
    store.log(job_id, "info", "FRED api_key=abcd1234 was used by owner@example.com")
    store.log(job_id, "warning", "Authorization: Bearer abc.def")
    store.alert(job_id, f"checkpoint {SHA} token=xyz")
    lines = store.logs(job_id)
    text = " ".join(line.message for line in lines)
    assert "abcd1234" not in text
    assert "example.com" not in text
    assert "abc.def" not in text
    assert SHA not in text
    assert "xyz" not in text
    assert [line.seq for line in store.logs(job_id, after=lines[1].seq)] == [
        line.seq for line in lines[2:]
    ]
    assert len(store.get(job_id).alerts) == 1
    assert redact("x" * 1000) == "x" * 400


def test_an_estimate_is_shown_and_a_long_or_unbounded_job_refused(store: JobStore) -> None:
    free = estimate(request(max_epochs=80, device="cuda"))
    assert 0 < free.seconds < 3600
    assert free.cost_usd == 0
    assert "measured" in free.basis
    paid = estimate(request(max_epochs=80, device="cuda", rate_usd_per_hour=2.0))
    assert paid.cost_usd > 0
    cpu = estimate(request(max_epochs=80, device="cpu"))
    assert cpu.seconds > free.seconds
    assert cpu.vram_mb == 0
    long = request(max_runtime_seconds=MAX_RUNTIME_SECONDS + 1)
    assert refusals(long)
    with pytest.raises(JobError, match="overnight"):
        store.submit(long, ESTIMATE)
    assert not refusals(request(max_runtime_seconds=MAX_RUNTIME_SECONDS + 1, overnight=True))
    with pytest.raises(JobError, match="spend limit"):
        store.submit(request(rate_usd_per_hour=1.0), ESTIMATE)
