"""The durable queue: SQLite in WAL mode, one short connection per call.

A worker takes a job with a lease and keeps it alive with heartbeats. A lease that runs
out means the worker died: the next worker takes the job and goes on from its checkpoint.
Everything that changes a job is one transaction, so a crash leaves it in a named state.

- ``submit`` is idempotent: the job id is the hash of the idempotency key, the same key
  with the same request returns the same job, with another request it is refused;
- a job waits in the queue until its estimate is approved;
- pause and stop are requests: they wait in the job until the worker reaches a safe point;
- resume puts a job back in the queue with the budget it already used.
"""

import hashlib
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from multiverse_contracts.forecasting import EpochLog
from multiverse_contracts.jobs import (
    JobDetail,
    JobEstimate,
    JobLogLine,
    JobRequest,
    JobStatus,
    JobView,
)
from multiverse_jobs.estimate import refusals
from multiverse_jobs.redact import redact

DEFAULT_BATCH = 256
DEFAULT_ATTEMPTS = 3
Command = Literal["pause", "stop"]
Level = Literal["info", "warning", "error"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    request TEXT NOT NULL,
    estimate TEXT NOT NULL,
    status TEXT NOT NULL,
    command TEXT,
    approved_by TEXT,
    approved_at TEXT,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    epoch INTEGER NOT NULL DEFAULT 0,
    best_epoch INTEGER,
    best_loss REAL,
    train_loss REAL,
    validation_loss REAL,
    batch_size INTEGER NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    elapsed REAL NOT NULL DEFAULT 0,
    worker TEXT,
    pid INTEGER,
    lease_until TEXT,
    last_heartbeat TEXT,
    reason TEXT,
    checkpoint_sha256 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
    job_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (job_id, epoch)
);
CREATE TABLE IF NOT EXISTS logs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    at TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    job_id TEXT NOT NULL,
    at TEXT NOT NULL,
    message TEXT NOT NULL
);
"""
ALLOWED: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.VALIDATING, JobStatus.STOPPED}),
    JobStatus.VALIDATING: frozenset(
        {
            JobStatus.RUNNING,
            JobStatus.PAUSE_REQUESTED,
            JobStatus.STOP_REQUESTED,
            JobStatus.QUEUED,
            JobStatus.FAILED,
            JobStatus.VALIDATING,
        }
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.PAUSE_REQUESTED,
            JobStatus.STOP_REQUESTED,
            JobStatus.STOPPED,
            JobStatus.QUEUED,
            JobStatus.FAILED,
            JobStatus.COMPLETED,
            JobStatus.VALIDATING,
        }
    ),
    JobStatus.PAUSE_REQUESTED: frozenset(
        {
            JobStatus.PAUSED,
            JobStatus.STOP_REQUESTED,
            JobStatus.STOPPED,
            JobStatus.QUEUED,
            JobStatus.FAILED,
            JobStatus.COMPLETED,
            JobStatus.VALIDATING,
        }
    ),
    JobStatus.STOP_REQUESTED: frozenset(
        {
            JobStatus.STOPPED,
            JobStatus.QUEUED,
            JobStatus.FAILED,
            JobStatus.COMPLETED,
            JobStatus.VALIDATING,
        }
    ),
    JobStatus.PAUSED: frozenset({JobStatus.QUEUED, JobStatus.STOPPED}),
    JobStatus.STOPPED: frozenset({JobStatus.QUEUED}),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
    JobStatus.COMPLETED: frozenset(),
}
HELD = (
    JobStatus.VALIDATING,
    JobStatus.RUNNING,
    JobStatus.PAUSE_REQUESTED,
    JobStatus.STOP_REQUESTED,
)


class JobError(ValueError):
    """A request the state of the job does not allow."""


class LeaseLostError(RuntimeError):
    """Another worker owns the job now: this one must stop touching it."""


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _moment(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def job_id_of(idempotency_key: str) -> str:
    return "job-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]


class JobStore:
    def __init__(self, path: Path, clock: Callable[[], datetime] | None = None) -> None:
        self.path = path
        self.clock = clock if clock is not None else (lambda: datetime.now(UTC))
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._open() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def _open(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")

    def _row(self, db: sqlite3.Connection, job_id: str) -> sqlite3.Row:
        row: sqlite3.Row | None = db.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return row

    def _view(self, db: sqlite3.Connection, row: sqlite3.Row) -> JobView:
        request = JobRequest.model_validate_json(row["request"])
        alerts = db.execute(
            "SELECT message FROM alerts WHERE job_id = ? ORDER BY at", (row["job_id"],)
        ).fetchall()
        return JobView(
            job_id=row["job_id"],
            request=request,
            estimate=JobEstimate.model_validate_json(row["estimate"]),
            status=JobStatus(row["status"]),
            approved_by=row["approved_by"],
            approved_at=_moment(row["approved_at"]),
            attempt=row["attempt"],
            max_attempts=row["max_attempts"],
            epoch=row["epoch"],
            best_epoch=row["best_epoch"],
            best_validation_loss=row["best_loss"],
            train_loss=row["train_loss"],
            validation_loss=row["validation_loss"],
            batch_size=row["batch_size"],
            progress_percent=row["progress"],
            elapsed_seconds=row["elapsed"],
            spent_usd=row["elapsed"] / 3600 * request.rate_usd_per_hour,
            last_heartbeat=_moment(row["last_heartbeat"]),
            worker=row["worker"],
            reason=row["reason"],
            alerts=tuple(a["message"] for a in alerts),
            checkpoint_sha256=row["checkpoint_sha256"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _move(
        self, db: sqlite3.Connection, row: sqlite3.Row, status: JobStatus, **fields: object
    ) -> None:
        current = JobStatus(row["status"])
        if status not in ALLOWED[current]:
            raise JobError(f"{row['job_id']}: {current.value} cannot become {status.value}")
        self._update(db, row["job_id"], status=status.value, **fields)

    def _update(self, db: sqlite3.Connection, job_id: str, **fields: object) -> None:
        fields["updated_at"] = _stamp(self.clock())
        names = ", ".join(f"{name} = ?" for name in fields)
        db.execute(f"UPDATE jobs SET {names} WHERE job_id = ?", (*fields.values(), job_id))

    def _say(self, db: sqlite3.Connection, job_id: str, level: Level, message: str) -> None:
        db.execute(
            "INSERT INTO logs (job_id, at, level, message) VALUES (?, ?, ?, ?)",
            (job_id, _stamp(self.clock()), level, redact(message)),
        )

    def submit(
        self,
        request: JobRequest,
        estimate: JobEstimate,
        max_attempts: int = DEFAULT_ATTEMPTS,
    ) -> tuple[JobView, bool]:
        """The job and whether this call created it; a repeated call changes nothing."""
        problems = refusals(request)
        if problems:
            raise JobError("; ".join(problems))
        job_id = job_id_of(request.idempotency_key)
        text = request.model_dump_json()
        with self._write() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is not None:
                if row["request"] != text:
                    raise JobError(f"{job_id}: this key was used for another request")
                return self._view(db, row), False
            now = _stamp(self.clock())
            db.execute(
                "INSERT INTO jobs (job_id, idempotency_key, request, estimate, status, "
                "max_attempts, batch_size, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    request.idempotency_key,
                    text,
                    estimate.model_dump_json(),
                    JobStatus.QUEUED.value,
                    max_attempts,
                    DEFAULT_BATCH,
                    now,
                    now,
                ),
            )
            self._say(db, job_id, "info", f"submitted by {request.owner}, awaiting approval")
            return self._view(db, self._row(db, job_id)), True

    def get(self, job_id: str) -> JobView:
        with self._open() as db:
            return self._view(db, self._row(db, job_id))

    def jobs(self) -> list[JobView]:
        with self._open() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC, job_id").fetchall()
            return [self._view(db, row) for row in rows]

    def detail(self, job_id: str) -> JobDetail:
        with self._open() as db:
            view = self._view(db, self._row(db, job_id))
            rows = db.execute(
                "SELECT payload FROM metrics WHERE job_id = ? ORDER BY epoch", (job_id,)
            ).fetchall()
        return JobDetail(
            job=view, metrics=tuple(EpochLog.model_validate_json(r["payload"]) for r in rows)
        )

    def logs(self, job_id: str, after: int = 0, limit: int = 200) -> list[JobLogLine]:
        with self._open() as db:
            self._row(db, job_id)
            rows = db.execute(
                "SELECT * FROM logs WHERE job_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                (job_id, after, limit),
            ).fetchall()
        return [
            JobLogLine(
                seq=r["seq"],
                at=datetime.fromisoformat(r["at"]),
                level=r["level"],
                message=r["message"],
            )
            for r in rows
        ]

    def approve(self, job_id: str, by: str) -> JobView:
        with self._write() as db:
            row = self._row(db, job_id)
            if row["approved_at"] is None:
                self._update(db, job_id, approved_by=by, approved_at=_stamp(self.clock()))
                self._say(db, job_id, "info", f"estimate approved by {by}")
            return self._view(db, self._row(db, job_id))

    def lease(self, worker: str, pid: int, ttl_seconds: float) -> JobView | None:
        """The oldest job that is waiting or whose worker died; None when there is none."""
        now = self.clock()
        with self._write() as db:
            held = ", ".join(f"'{s.value}'" for s in HELD)
            row = db.execute(
                "SELECT * FROM jobs WHERE (status = 'queued' AND approved_at IS NOT NULL) "
                f"OR (status IN ({held}) AND lease_until < ?) ORDER BY created_at, job_id LIMIT 1",
                (_stamp(now),),
            ).fetchone()
            if row is None:
                return None
            job_id = row["job_id"]
            died = JobStatus(row["status"]) in HELD
            if died:
                self._say(db, job_id, "warning", f"worker {row['worker']} stopped answering")
            if row["attempt"] >= row["max_attempts"]:
                self._move(
                    db,
                    row,
                    JobStatus.FAILED,
                    reason=f"gave up after {row['attempt']} attempts",
                    worker=None,
                    pid=None,
                    lease_until=None,
                )
                self._say(db, job_id, "error", "gave up: no attempts left")
                return None
            self._move(
                db,
                row,
                JobStatus.VALIDATING,
                attempt=row["attempt"] + 1,
                worker=worker,
                pid=pid,
                lease_until=_stamp(now + timedelta(seconds=ttl_seconds)),
                last_heartbeat=_stamp(now),
                reason=None,
            )
            self._say(db, job_id, "info", f"taken by {worker}, attempt {row['attempt'] + 1}")
            return self._view(db, self._row(db, job_id))

    def _owned(self, db: sqlite3.Connection, job_id: str, worker: str) -> sqlite3.Row:
        row = self._row(db, job_id)
        if row["worker"] != worker:
            raise LeaseLostError(f"{job_id} belongs to {row['worker']}, not to {worker}")
        return row

    def started(self, job_id: str, worker: str) -> JobView:
        """Validation passed; a request made meanwhile stays visible."""
        with self._write() as db:
            row = self._owned(db, job_id, worker)
            wanted = {
                "pause": JobStatus.PAUSE_REQUESTED,
                "stop": JobStatus.STOP_REQUESTED,
                None: JobStatus.RUNNING,
            }[row["command"]]
            self._move(db, row, wanted)
            self._say(db, job_id, "info", "running")
            return self._view(db, self._row(db, job_id))

    def heartbeat(self, job_id: str, worker: str, ttl_seconds: float) -> Command | None:
        """Keeps the lease and tells the worker what was asked of it."""
        now = self.clock()
        with self._write() as db:
            row = self._owned(db, job_id, worker)
            self._update(
                db,
                job_id,
                lease_until=_stamp(now + timedelta(seconds=ttl_seconds)),
                last_heartbeat=_stamp(now),
            )
            command: Command | None = row["command"]
            return command

    def epoch_done(
        self,
        job_id: str,
        worker: str,
        log: EpochLog,
        best_epoch: int,
        best_loss: float,
        elapsed: float,
        checkpoint_sha256: str | None,
    ) -> JobView:
        with self._write() as db:
            row = self._owned(db, job_id, worker)
            request = JobRequest.model_validate_json(row["request"])
            self._update(
                db,
                job_id,
                epoch=log.epoch,
                best_epoch=best_epoch,
                best_loss=best_loss,
                train_loss=log.train_loss,
                validation_loss=log.validation_loss,
                progress=min(100.0, 100.0 * log.epoch / request.max_epochs),
                elapsed=elapsed,
                checkpoint_sha256=checkpoint_sha256,
            )
            db.execute(
                "INSERT OR REPLACE INTO metrics (job_id, epoch, payload) VALUES (?, ?, ?)",
                (job_id, log.epoch, log.model_dump_json()),
            )
            self._say(
                db,
                job_id,
                "info",
                f"epoch {log.epoch}: train {log.train_loss:.4f}, "
                f"validation {log.validation_loss:.4f}",
            )
            return self._view(db, self._row(db, job_id))

    def log(self, job_id: str, level: Level, message: str) -> None:
        with self._write() as db:
            self._row(db, job_id)
            self._say(db, job_id, level, message)

    def alert(self, job_id: str, message: str) -> None:
        with self._write() as db:
            self._row(db, job_id)
            db.execute(
                "INSERT INTO alerts (job_id, at, message) VALUES (?, ?, ?)",
                (job_id, _stamp(self.clock()), redact(message)),
            )
            self._say(db, job_id, "error", message)

    def finish(self, job_id: str, worker: str, status: JobStatus, reason: str) -> JobView:
        """A final or waiting state: the worker lets go of the job."""
        with self._write() as db:
            row = self._owned(db, job_id, worker)
            extra: dict[str, object] = {}
            if status is JobStatus.COMPLETED:
                extra["progress"] = 100.0
            self._move(
                db,
                row,
                status,
                reason=redact(reason),
                command=None,
                worker=None,
                pid=None,
                lease_until=None,
                **extra,
            )
            self._say(db, job_id, "info", f"{status.value}: {reason}")
            return self._view(db, self._row(db, job_id))

    def retry(
        self, job_id: str, worker: str, reason: str, batch_size: int | None = None
    ) -> JobView:
        """Back in the queue after a failure worth retrying, or failed when none is left."""
        with self._write() as db:
            row = self._owned(db, job_id, worker)
            last = row["attempt"] >= row["max_attempts"]
            status = JobStatus.FAILED if last else JobStatus.QUEUED
            self._move(
                db,
                row,
                status,
                reason=redact(reason),
                worker=None,
                pid=None,
                lease_until=None,
                batch_size=batch_size if batch_size is not None else row["batch_size"],
            )
            self._say(db, job_id, "warning", f"{status.value} after: {reason}")
            return self._view(db, self._row(db, job_id))

    def request_pause(self, job_id: str) -> JobView:
        return self._request(job_id, "pause", JobStatus.PAUSE_REQUESTED, JobStatus.PAUSED)

    def request_stop(self, job_id: str) -> JobView:
        return self._request(job_id, "stop", JobStatus.STOP_REQUESTED, JobStatus.STOPPED)

    def _request(
        self, job_id: str, command: Command, requested: JobStatus, idle: JobStatus
    ) -> JobView:
        """A job with a worker gets the request; a job without one moves at once."""
        with self._write() as db:
            row = self._row(db, job_id)
            status = JobStatus(row["status"])
            if status is JobStatus.VALIDATING:
                self._update(db, job_id, command=command)
            elif status in HELD:
                self._move(db, row, requested, command=command)
            elif status is JobStatus.QUEUED and command == "stop":
                self._move(db, row, JobStatus.STOPPED, reason="stopped before it started")
            elif status is JobStatus.PAUSED and command == "stop":
                self._move(db, row, idle, reason="stopped while paused")
            else:
                raise JobError(f"{job_id}: cannot {command} a job that is {status.value}")
            self._say(db, job_id, "info", f"{command} requested")
            return self._view(db, self._row(db, job_id))

    def resume(self, job_id: str) -> JobView:
        """Back in the queue from where it stopped, with the budget it already used."""
        with self._write() as db:
            row = self._row(db, job_id)
            status = JobStatus(row["status"])
            if status not in (JobStatus.PAUSED, JobStatus.STOPPED, JobStatus.FAILED):
                raise JobError(f"{job_id}: cannot resume a job that is {status.value}")
            self._move(
                db,
                row,
                JobStatus.QUEUED,
                reason=None,
                command=None,
                attempt=0 if status is JobStatus.FAILED else row["attempt"],
            )
            self._say(db, job_id, "info", "resume requested")
            return self._view(db, self._row(db, job_id))

    def pid(self, job_id: str) -> int | None:
        with self._open() as db:
            found: int | None = self._row(db, job_id)["pid"]
            return found
