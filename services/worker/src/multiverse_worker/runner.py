"""The worker loop: take a job, keep its lease alive, end it in a named state.

The trainer is a protocol, so the rules here run without PyTorch:

- a job that fails validation or an incompatible checkpoint fails at once, without retry;
- a loss that is not finite raises an alert and fails: more epochs would not help;
- out of device memory: retry from the checkpoint with half the batch;
- any other error: retry from the checkpoint until the attempts are used up;
- after each epoch, on a state already safe on disk, budgets and requests are checked.

A heartbeat thread keeps the lease during a long epoch. A lost lease means another worker
owns the job: this one drops it and writes nothing more.
"""

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from multiverse_contracts.forecasting import EpochLog
from multiverse_contracts.jobs import JobStatus, JobView
from multiverse_jobs.store import JobStore, LeaseLostError

log = logging.getLogger("multiverse_worker")
MIN_BATCH = 16
Decision = Literal["continue", "pause", "stop"]


class DeviceMemoryError(RuntimeError):
    """The device ran out of memory: a smaller batch may fit."""


class RefusedError(ValueError):
    """The job cannot run as asked: no retry would change that."""


class Trainer(Protocol):
    def validate(self, job: JobView) -> None: ...

    def run(self, job: JobView, session: "Session") -> Decision: ...


@dataclass
class Session:
    """What a trainer reports after each epoch; the answer is what to do next."""

    store: JobStore
    job: JobView
    worker: str
    ttl_seconds: float
    clock: Callable[[], float] = time.monotonic
    started: float = 0.0
    reason: str = "finished"
    lease_lost: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.started = self.clock()

    @property
    def elapsed(self) -> float:
        return self.job.elapsed_seconds + self.clock() - self.started

    def after_epoch(
        self, entry: EpochLog, best_epoch: int, best_loss: float, checkpoint_sha256: str | None
    ) -> Decision:
        if self.lease_lost.is_set():
            raise LeaseLostError(f"{self.job.job_id} was taken by another worker")
        view = self.store.epoch_done(
            self.job.job_id,
            self.worker,
            entry,
            best_epoch,
            best_loss,
            self.elapsed,
            checkpoint_sha256,
        )
        return self._answer(view, f"epoch {entry.epoch}")

    def after_batch(self, batches: int, paths: int, total: int, checkpoint_sha256: str) -> Decision:
        """The safe point of a Monte Carlo run: the batch is on disk, ask what to do next."""
        if self.lease_lost.is_set():
            raise LeaseLostError(f"{self.job.job_id} was taken by another worker")
        view = self.store.batch_done(
            self.job.job_id, self.worker, batches, paths, total, self.elapsed, checkpoint_sha256
        )
        return self._answer(view, f"{paths} paths")

    def _answer(self, view: JobView, where: str) -> Decision:
        request = view.request
        if view.elapsed_seconds >= request.max_runtime_seconds:
            self.reason = f"budget: runtime limit of {request.max_runtime_seconds} s reached"
            return "stop"
        if request.rate_usd_per_hour > 0 and view.spent_usd >= request.spend_limit_usd:
            self.reason = f"budget: spend limit of {request.spend_limit_usd} USD reached"
            return "stop"
        command = self.store.heartbeat(self.job.job_id, self.worker, self.ttl_seconds)
        if command is not None:
            self.reason = f"{command} at a safe point, {where}"
            return command
        return "continue"


def _beat(session: Session, done: threading.Event) -> None:
    while not done.wait(session.ttl_seconds / 3):
        try:
            session.store.heartbeat(session.job.job_id, session.worker, session.ttl_seconds)
        except LeaseLostError:
            session.lease_lost.set()
            return


def work_once(
    store: JobStore,
    trainer: Trainer,
    worker: str,
    ttl_seconds: float,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """One job from lease to a named state; False when nothing was waiting."""
    job = store.lease(worker, os.getpid(), ttl_seconds)
    if job is None:
        return False
    session = Session(store, job, worker, ttl_seconds, clock)
    done = threading.Event()
    beat = threading.Thread(target=_beat, args=(session, done), daemon=True)
    beat.start()
    try:
        _work(store, trainer, job, session, worker)
    except LeaseLostError as error:
        log.warning("%s", error)
    finally:
        done.set()
        beat.join()
    return True


def _work(store: JobStore, trainer: Trainer, job: JobView, session: Session, worker: str) -> None:
    job_id = job.job_id
    try:
        trainer.validate(job)
        current = store.started(job_id, worker)
        decision = trainer.run(current, session)
    except RefusedError as error:
        store.alert(job_id, f"refused: {error}")
        store.finish(job_id, worker, JobStatus.FAILED, f"refused: {error}")
    except FloatingPointError as error:
        store.alert(job_id, f"not a number: {error}")
        store.finish(job_id, worker, JobStatus.FAILED, f"not a number: {error}")
    except DeviceMemoryError as error:
        smaller = max(MIN_BATCH, store.get(job_id).batch_size // 2)
        store.alert(job_id, f"out of memory, batch {smaller} next: {error}")
        store.retry(job_id, worker, "out of device memory", batch_size=smaller)
    except LeaseLostError:
        raise
    except Exception as error:
        store.log(job_id, "error", f"{type(error).__name__}: {error}")
        store.retry(job_id, worker, f"{type(error).__name__}: {error}")
    else:
        if decision == "continue":
            store.finish(job_id, worker, JobStatus.COMPLETED, session.reason)
        elif decision == "pause":
            store.finish(job_id, worker, JobStatus.PAUSED, session.reason)
        else:
            store.finish(job_id, worker, JobStatus.STOPPED, session.reason)


def work(
    store: JobStore,
    trainer: Trainer,
    worker: str,
    ttl_seconds: float,
    *,
    watch_seconds: float = 0.0,
    max_jobs: int | None = None,
) -> int:
    """Jobs until the queue is empty: a worker never waits by itself unless told to."""
    count = 0
    limit = time.monotonic() + watch_seconds
    while max_jobs is None or count < max_jobs:
        if work_once(store, trainer, worker, ttl_seconds):
            count += 1
            continue
        if time.monotonic() >= limit:
            break
        time.sleep(1.0)
    return count
