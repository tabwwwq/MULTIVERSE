"""Monte Carlo jobs: the same queue, stops at a batch, and the numbers survive a stop."""

import json
from pathlib import Path
from typing import Any

import pytest
from multiverse_simulation.example import default_decision, illustrative_case

from multiverse_contracts.decisions import DECISION_MODELS
from multiverse_contracts.jobs import JobEstimate, JobRequest, JobStatus, JobView, parse_request
from multiverse_contracts.simulation import (
    SimulationReport,
    SimulationRequest,
    SimulationSettings,
)
from multiverse_jobs.estimate import estimate, simulation_estimate
from multiverse_jobs.store import JobStore
from multiverse_worker.runner import Decision, RefusedError, Session, work_once
from multiverse_worker.simulation import Dispatcher, SimulationRunner

CASE = illustrative_case(horizon=8, history_quarters=40)


def request(key: str = "stage-22-test-run", **changes: Any) -> SimulationRequest:
    kind = "capex_expansion"
    decision = DECISION_MODELS[kind].model_validate_json(json.dumps(default_decision(kind)))
    values: dict[str, Any] = {
        "idempotency_key": key,
        "owner": "owner",
        "case_id": CASE.case_id,
        "decision": decision,
        "settings": SimulationSettings(paths=30, seed=9, batch_paths=10),
        "max_runtime_seconds": 600,
    } | changes
    return SimulationRequest(**values)


class NoTraining:
    def validate(self, job: JobView) -> None:
        raise RefusedError("this test has no training")

    def run(self, job: JobView, session: Session) -> Decision:
        raise AssertionError("a simulation must not reach the trainer")


@pytest.fixture
def setup(tmp_path: Path) -> tuple[JobStore, Dispatcher, SimulationRunner]:
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / f"{CASE.case_id}.json").write_text(CASE.model_dump_json(), encoding="utf-8")
    store = JobStore(tmp_path / "jobs.sqlite")
    runner = SimulationRunner(tmp_path, cases)
    return store, Dispatcher(NoTraining(), runner), runner


def queued(store: JobStore, simulation: SimulationRequest) -> JobView:
    job, _ = store.submit(simulation, estimate(simulation))
    return store.approve(job.job_id, "owner")


def report_of(runner: SimulationRunner, job: JobView) -> SimulationReport:
    return SimulationReport.model_validate_json((runner.folder(job) / "report.json").read_bytes())


def test_a_job_runs_to_a_report(setup: tuple[JobStore, Dispatcher, SimulationRunner]) -> None:
    store, dispatcher, runner = setup
    job = queued(store, request())
    assert work_once(store, dispatcher, "worker", 60)
    done = store.get(job.job_id)
    assert done.status is JobStatus.COMPLETED
    assert done.progress_percent == 100
    assert done.epoch == 3
    assert done.checkpoint_sha256 is not None
    report = report_of(runner, done)
    assert report.diagnostics.paths == 30
    assert report.manifest.report_id in (done.reason or "")


def test_nothing_runs_before_the_estimate_is_approved(
    setup: tuple[JobStore, Dispatcher, SimulationRunner],
) -> None:
    store, dispatcher, _ = setup
    store.submit(request(), estimate(request()))
    assert not work_once(store, dispatcher, "worker", 60)


def stop_after_first_batch(store: JobStore, job_id: str) -> None:
    real = store.batch_done

    def wrapped(*args: Any) -> JobView:
        view = real(*args)
        store.batch_done = real  # type: ignore[method-assign]
        store.request_stop(job_id)
        return view

    store.batch_done = wrapped  # type: ignore[method-assign]


def test_a_stop_waits_for_a_batch_and_a_resume_ends_in_the_same_numbers(
    setup: tuple[JobStore, Dispatcher, SimulationRunner],
) -> None:
    store, dispatcher, runner = setup
    whole = queued(store, request("stage-22-whole-run"))
    work_once(store, dispatcher, "worker", 60)
    whole = store.get(whole.job_id)

    job = queued(store, request("stage-22-stop-run"))
    stop_after_first_batch(store, job.job_id)
    work_once(store, dispatcher, "worker", 60)
    stopped = store.get(job.job_id)
    assert stopped.status is JobStatus.STOPPED
    assert stopped.progress_percent == pytest.approx(100 / 3)
    assert "10 paths" in (stopped.reason or "")
    assert not (runner.folder(stopped) / "report.json").exists()

    store.resume(job.job_id)
    store.approve(job.job_id, "owner")
    work_once(store, dispatcher, "worker", 60)
    resumed = store.get(job.job_id)
    assert resumed.status is JobStatus.COMPLETED
    first, second = report_of(runner, whole), report_of(runner, resumed)
    assert first.manifest.report_id == second.manifest.report_id
    assert first.result.metrics == second.result.metrics
    assert first.risks == second.risks


def test_the_runtime_budget_stops_at_a_batch(
    setup: tuple[JobStore, Dispatcher, SimulationRunner],
) -> None:
    store, dispatcher, _ = setup
    job = queued(store, request(max_runtime_seconds=1))
    ticks = iter(range(0, 10_000, 5))
    work_once(store, dispatcher, "worker", 60, clock=lambda: float(next(ticks)))
    stopped = store.get(job.job_id)
    assert stopped.status is JobStatus.STOPPED
    assert "budget" in (stopped.reason or "")


def test_a_case_that_does_not_exist_fails_without_retry(
    setup: tuple[JobStore, Dispatcher, SimulationRunner],
) -> None:
    store, dispatcher, _ = setup
    job = queued(store, request(case_id="case-missing"))
    work_once(store, dispatcher, "worker", 60)
    failed = store.get(job.job_id)
    assert failed.status is JobStatus.FAILED
    assert "no case" in (failed.reason or "")
    assert failed.attempt == 1


def test_the_estimate_is_measured_and_grows_with_paths() -> None:
    small = simulation_estimate(
        request(settings=SimulationSettings(paths=3000, seed=9, batch_paths=10))
    )
    large = simulation_estimate(
        request(settings=SimulationSettings(paths=30_000, seed=9, batch_paths=10))
    )
    assert isinstance(small, JobEstimate)
    assert large.seconds == pytest.approx(small.seconds * 10, rel=0.01)
    assert large.vram_mb == 0
    assert "measured" in large.basis


def test_rows_stored_before_stage_22_are_still_trainings() -> None:
    stored = {
        "idempotency_key": "stage-18-test-run",
        "owner": "owner",
        "model": "gru_attention",
        "dataset_id": "fds-20261028-abababababab",
        "dataset_sha256": "ab" * 32,
        "protocol_path": "protocol.json",
        "fold_year": 2026,
        "seed": 1,
        "max_epochs": 5,
        "max_runtime_seconds": 600,
        "spend_limit_usd": 0,
    }
    found = parse_request(json.dumps(stored))
    assert isinstance(found, JobRequest)
    assert found.kind == "training"


def test_a_stored_simulation_reads_back_as_one() -> None:
    assert isinstance(parse_request(request().model_dump_json()), SimulationRequest)
