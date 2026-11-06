"""The durable queue: SQLite in WAL mode, one short connection per call.

A worker takes a job with a lease and keeps it alive with heartbeats. A lease that runs
out means the worker died: the next worker takes the job and goes on from its checkpoint.
Everything that changes a job is one transaction, so a crash leaves it in a named state.

- ``submit`` is idempotent: the job id is the hash of the owner and the idempotency key, the
  same key with the same request returns the same job, with another request it is refused;
- a job waits in the queue until its estimate is approved;
- limits are checked here, so that no way into the queue goes around them (Stage 24);
- pause and stop are requests: they wait in the job until the worker reaches a safe point;
- resume puts a job back in the queue with the budget it already used.
"""

import hashlib
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from multiverse_contracts.forecasting import EpochLog
from multiverse_contracts.jobs import (
    AccountExport,
    AuditRow,
    Erasure,
    JobDetail,
    JobEstimate,
    JobLogLine,
    JobRequest,
    JobStatus,
    JobView,
    parse_request,
)
from multiverse_contracts.simulation import SimulationRequest
from multiverse_jobs.estimate import refusals
from multiverse_jobs.redact import redact

DEFAULT_BATCH = 256
DEFAULT_ATTEMPTS = 3
Command = Literal["pause", "stop"]
Level = Literal["info", "warning", "error"]
Outcome = Literal["allowed", "denied", "not_found", "limited"]
LIST_LIMIT = 200
ERASED = "erased"

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
    updated_at TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT ''
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
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    job_id TEXT,
    outcome TEXT NOT NULL
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


FINISHED = (JobStatus.STOPPED, JobStatus.FAILED, JobStatus.COMPLETED)


@dataclass(frozen=True)
class Limits:
    """What the queue accepts. Paid compute is off until the owner sets a limit above zero."""

    cloud_spend_usd: float = 0.0
    active_jobs: int = 8
    daily_compute_seconds: float = 43_200.0


class JobError(ValueError):
    """A request the state of the job does not allow."""


class LimitError(JobError):
    """A request over a limit: refused whatever the state of the job."""


class LeaseLostError(RuntimeError):
    """Another worker owns the job now: this one must stop touching it."""


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _moment(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def scoped(owner: str, idempotency_key: str) -> str:
    """Keys belong to their owner: the same key of another owner is another job."""
    return f"{owner}/{idempotency_key}"


def job_id_of(owner: str, idempotency_key: str) -> str:
    return "job-" + hashlib.sha256(scoped(owner, idempotency_key).encode()).hexdigest()[:12]


class JobStore:
    def __init__(
        self,
        path: Path,
        clock: Callable[[], datetime] | None = None,
        limits: Limits | None = None,
    ) -> None:
        self.path = path
        self.clock = clock if clock is not None else (lambda: datetime.now(UTC))
        self.limits = limits if limits is not None else Limits()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._open() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Queues older than Stage 24 had no owner column: the request always named one."""
        with self._write() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
            if "owner" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE jobs SET owner = json_extract(request, '$.owner') WHERE owner = ''")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_owner ON jobs (owner)")

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
        request = parse_request(row["request"])
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
        request: JobRequest | SimulationRequest,
        estimate: JobEstimate,
        max_attempts: int = DEFAULT_ATTEMPTS,
    ) -> tuple[JobView, bool]:
        """The job and whether this call created it; a repeated call changes nothing."""
        problems = refusals(request)
        if problems:
            raise JobError("; ".join(problems))
        job_id = job_id_of(request.owner, request.idempotency_key)
        text = request.model_dump_json()
        with self._write() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is not None:
                if row["request"] != text:
                    raise JobError(f"{job_id}: this key was used for another request")
                return self._view(db, row), False
            self._within_limits(db, request, estimate)
            now = _stamp(self.clock())
            db.execute(
                "INSERT INTO jobs (job_id, owner, idempotency_key, request, estimate, status, "
                "max_attempts, batch_size, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    request.owner,
                    scoped(request.owner, request.idempotency_key),
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

    def _reserved(self, db: sqlite3.Connection, other_than: str | None = None) -> float:
        """Spent by finished jobs, and all a job may still spend until it finishes."""
        total = 0.0
        for row in db.execute("SELECT job_id, request, status, elapsed FROM jobs"):
            request = parse_request(row["request"])
            if request.rate_usd_per_hour == 0 or row["job_id"] == other_than:
                continue
            done = JobStatus(row["status"]) is JobStatus.COMPLETED
            spent = row["elapsed"] / 3600 * request.rate_usd_per_hour
            total += spent if done else request.spend_limit_usd
        return total

    def _within_spending(
        self,
        db: sqlite3.Connection,
        request: JobRequest | SimulationRequest,
        job_id: str | None = None,
    ) -> None:
        if request.rate_usd_per_hour == 0:
            return
        cap = self.limits.cloud_spend_usd
        if cap == 0:
            raise LimitError("paid compute is off: the cloud spending limit is zero")
        reserved = self._reserved(db, job_id)
        if reserved + request.spend_limit_usd > cap:
            raise LimitError(
                f"{request.spend_limit_usd} USD more would pass the cloud spending limit: "
                f"{reserved} of {cap} USD is taken"
            )

    def _within_limits(
        self,
        db: sqlite3.Connection,
        request: JobRequest | SimulationRequest,
        estimate: JobEstimate,
    ) -> None:
        self._within_spending(db, request)
        if estimate.cost_usd > request.spend_limit_usd:
            raise LimitError(
                f"the estimate of {estimate.cost_usd} USD is above the job's own limit"
            )
        finished = ", ".join(f"'{s.value}'" for s in FINISHED)
        active: int = db.execute(
            f"SELECT COUNT(*) FROM jobs WHERE owner = ? AND status NOT IN ({finished})",
            (request.owner,),
        ).fetchone()[0]
        if active >= self.limits.active_jobs:
            raise LimitError(f"{active} jobs of {request.owner} are waiting or running")
        day_ago = _stamp(self.clock() - timedelta(days=1))
        rows = db.execute(
            "SELECT request FROM jobs WHERE owner = ? AND created_at >= ?",
            (request.owner, day_ago),
        ).fetchall()
        asked = sum(parse_request(row["request"]).max_runtime_seconds for row in rows)
        if asked + request.max_runtime_seconds > self.limits.daily_compute_seconds:
            raise LimitError(
                f"{request.owner} asked for {asked} s of compute in 24 hours; the limit is "
                f"{self.limits.daily_compute_seconds} s"
            )

    def get(self, job_id: str) -> JobView:
        with self._open() as db:
            return self._view(db, self._row(db, job_id))

    def owner_of(self, job_id: str) -> str:
        with self._open() as db:
            owner: str = self._row(db, job_id)["owner"]
            return owner

    def jobs(self, owner: str | None = None, limit: int = LIST_LIMIT) -> list[JobView]:
        """The newest jobs; of one owner when asked, so nobody reads a list and filters it."""
        where, values = ("WHERE owner = ?", (owner,)) if owner is not None else ("", ())
        with self._open() as db:
            rows = db.execute(
                f"SELECT * FROM jobs {where} ORDER BY created_at DESC, job_id LIMIT ?",
                (*values, limit),
            ).fetchall()
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
                self._within_spending(db, parse_request(row["request"]), job_id)
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
            try:
                self._within_spending(db, parse_request(row["request"]), job_id)
            except LimitError as error:
                # A cap lowered after approval holds here too: no worker pays for this job.
                self._move(db, row, JobStatus.STOPPED, reason=redact(str(error)), lease_until=None)
                self._say(db, job_id, "warning", f"not started: {error}")
                return None
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

    def batch_done(
        self,
        job_id: str,
        worker: str,
        batches: int,
        paths: int,
        total: int,
        elapsed: float,
        checkpoint_sha256: str,
    ) -> JobView:
        """A batch of paths is safe on disk: the Monte Carlo counterpart of an epoch."""
        with self._write() as db:
            self._owned(db, job_id, worker)
            self._update(
                db,
                job_id,
                epoch=batches,
                progress=min(100.0, 100.0 * paths / total),
                elapsed=elapsed,
                checkpoint_sha256=checkpoint_sha256,
            )
            self._say(db, job_id, "info", f"{paths} of {total} paths")
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

    def audit(self, actor: str, action: str, job_id: str | None, outcome: Outcome) -> None:
        """Every protected read and action, allowed or not (docs/12)."""
        with self._write() as db:
            db.execute(
                "INSERT INTO audit (at, actor, action, job_id, outcome) VALUES (?, ?, ?, ?, ?)",
                (_stamp(self.clock()), actor, action, job_id, outcome),
            )

    def audit_rows(
        self, actor: str | None = None, after: int = 0, limit: int = LIST_LIMIT
    ) -> list[AuditRow]:
        where = "AND actor = ?" if actor is not None else ""
        values = (actor,) if actor is not None else ()
        with self._open() as db:
            rows = db.execute(
                f"SELECT * FROM audit WHERE seq > ? {where} ORDER BY seq LIMIT ?",
                (after, *values, limit),
            ).fetchall()
        return [
            AuditRow(
                seq=r["seq"],
                at=datetime.fromisoformat(r["at"]),
                actor=r["actor"],
                action=r["action"],
                job_id=r["job_id"],
                outcome=r["outcome"],
            )
            for r in rows
        ]

    def prune_audit(self, days: int) -> int:
        """Rows past the retention period go: the data inventory promises it."""
        with self._write() as db:
            found = db.execute(
                "DELETE FROM audit WHERE at < ?",
                (_stamp(self.clock() - timedelta(days=days)),),
            )
            return found.rowcount

    def export_of(self, owner: str) -> AccountExport:
        details = [self.detail(job.job_id) for job in self.jobs(owner, limit=-1)]
        logs = [line for item in details for line in self.logs(item.job.job_id, limit=-1)]
        return AccountExport(
            principal=owner,
            exported_at=self.clock(),
            jobs=tuple(details),
            logs=tuple(logs),
            audit=tuple(self.audit_rows(owner, limit=-1)),
        )

    def erase(self, owner: str) -> Erasure:
        """Jobs of an owner go; a job still at work has to stop first.

        The caller removes the files of the returned jobs. Audit rows stay as a record that
        something happened, with the name gone.
        """
        with self._write() as db:
            found = db.execute(
                "SELECT job_id, status FROM jobs WHERE owner = ?", (owner,)
            ).fetchall()
            working = [r["job_id"] for r in found if JobStatus(r["status"]) in HELD]
            if working:
                raise JobError(f"stop these jobs first: {', '.join(working)}")
            ids = tuple(r["job_id"] for r in found)
            for table in ("metrics", "logs", "alerts", "jobs"):
                db.executemany(f"DELETE FROM {table} WHERE job_id = ?", ((i,) for i in ids))
            db.execute("UPDATE jobs SET approved_by = ? WHERE approved_by = ?", (ERASED, owner))
            changed = db.execute("UPDATE audit SET actor = ? WHERE actor = ?", (ERASED, owner))
            return Erasure(principal=owner, jobs_erased=ids, audit_rows_anonymized=changed.rowcount)
