"""Limits, ownership, audit, erasure and backups of the queue (Stage 24)."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from multiverse_contracts.jobs import JobEstimate, JobRequest, JobStatus
from multiverse_jobs import backup
from multiverse_jobs.store import JobError, JobStore, LimitError, Limits

SHA = "ab" * 32
FREE = JobEstimate(seconds=30, vram_mb=500, disk_mb=3, cost_usd=0, basis="invented")
START = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def request(key: str = "stage-24-test-run", **changes: Any) -> JobRequest:
    values: dict[str, Any] = {
        "idempotency_key": key,
        "owner": "alice",
        "model": "gru_attention",
        "dataset_id": f"fds-20261028-{SHA[:12]}",
        "dataset_sha256": SHA,
        "protocol_path": "data/protocols/stage-16-temporal-large.json",
        "fold_year": 2026,
        "seed": 1,
        "max_epochs": 5,
        "max_runtime_seconds": 600,
        "spend_limit_usd": 0,
    } | changes
    return JobRequest.model_validate(values)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def store_at(tmp_path: Path, clock: Clock | None = None, **limits: Any) -> JobStore:
    return JobStore(tmp_path / "jobs.sqlite", clock, Limits(**limits))


def test_paid_compute_is_off_by_default(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite")
    with pytest.raises(LimitError, match="paid compute is off"):
        store.submit(request(rate_usd_per_hour=1.0, spend_limit_usd=1.0), FREE)
    assert store.jobs() == []


def test_free_compute_passes_a_zero_limit(tmp_path: Path) -> None:
    job, created = JobStore(tmp_path / "jobs.sqlite").submit(request(), FREE)
    assert created
    assert job.status is JobStatus.QUEUED


def test_spending_limits_add_up_against_the_cloud_limit(tmp_path: Path) -> None:
    store = store_at(tmp_path, cloud_spend_usd=10.0)
    store.submit(request("first-key-1", rate_usd_per_hour=1.0, spend_limit_usd=6.0), FREE)
    with pytest.raises(LimitError, match="cloud spending limit"):
        store.submit(request("second-key-1", rate_usd_per_hour=1.0, spend_limit_usd=5.0), FREE)
    store.submit(request("third-key-1", rate_usd_per_hour=1.0, spend_limit_usd=4.0), FREE)


def test_the_cap_of_all_owners_is_one(tmp_path: Path) -> None:
    store = store_at(tmp_path, cloud_spend_usd=10.0)
    store.submit(request("first-key-1", rate_usd_per_hour=1.0, spend_limit_usd=6.0), FREE)
    other = request("first-key-1", owner="bob", rate_usd_per_hour=1.0, spend_limit_usd=5.0)
    with pytest.raises(LimitError, match="cloud spending limit"):
        store.submit(other, FREE)


def test_a_finished_job_counts_what_it_spent(tmp_path: Path) -> None:
    store = store_at(tmp_path, cloud_spend_usd=10.0)
    paid = request("first-key-1", rate_usd_per_hour=3600.0, spend_limit_usd=9.0)
    job, _ = store.submit(paid, FREE)
    store.approve(job.job_id, "root")
    store.lease("worker", 1, 60)
    store.started(job.job_id, "worker")
    with store._write() as db:
        store._update(db, job.job_id, elapsed=2.0)
    store.finish(job.job_id, "worker", JobStatus.COMPLETED, "done")
    store.submit(request("second-key-1", rate_usd_per_hour=1.0, spend_limit_usd=8.0), FREE)
    with pytest.raises(LimitError):
        store.submit(request("third-key-1", rate_usd_per_hour=1.0, spend_limit_usd=0.5), FREE)


def test_an_estimate_above_the_own_limit_is_refused(tmp_path: Path) -> None:
    store = store_at(tmp_path, cloud_spend_usd=10.0)
    costly = FREE.model_copy(update={"cost_usd": 5.0})
    with pytest.raises(LimitError, match="above the job"):
        store.submit(request(rate_usd_per_hour=1.0, spend_limit_usd=1.0), costly)


def test_a_cap_lowered_later_stops_the_approval(tmp_path: Path) -> None:
    store = store_at(tmp_path, cloud_spend_usd=10.0)
    job, _ = store.submit(request(rate_usd_per_hour=1.0, spend_limit_usd=6.0), FREE)
    lowered = store_at(tmp_path, cloud_spend_usd=5.0)
    with pytest.raises(LimitError):
        lowered.approve(job.job_id, "root")
    assert lowered.get(job.job_id).approved_at is None


def test_a_cap_lowered_after_approval_stops_the_worker(tmp_path: Path) -> None:
    store = store_at(tmp_path, cloud_spend_usd=10.0)
    job, _ = store.submit(request(rate_usd_per_hour=1.0, spend_limit_usd=6.0), FREE)
    store.approve(job.job_id, "root")
    lowered = store_at(tmp_path, cloud_spend_usd=0.0)
    assert lowered.lease("worker", 1, 60) is None
    found = lowered.get(job.job_id)
    assert found.status is JobStatus.STOPPED
    assert found.reason is not None
    assert "paid compute is off" in found.reason


def test_active_jobs_of_an_owner_have_a_limit(tmp_path: Path) -> None:
    store = store_at(tmp_path, active_jobs=2)
    store.submit(request("first-key-1"), FREE)
    second, _ = store.submit(request("second-key-1"), FREE)
    with pytest.raises(LimitError, match="waiting or running"):
        store.submit(request("third-key-1"), FREE)
    store.submit(request("third-key-1", owner="bob"), FREE)
    store.request_stop(second.job_id)
    store.submit(request("third-key-1"), FREE)


def test_a_repeated_submit_is_not_a_new_job_for_the_limits(tmp_path: Path) -> None:
    store = store_at(tmp_path, active_jobs=1)
    store.submit(request(), FREE)
    _, created = store.submit(request(), FREE)
    assert not created


def test_compute_asked_for_in_a_day_has_a_limit(tmp_path: Path) -> None:
    clock = Clock()
    store = store_at(tmp_path, clock, daily_compute_seconds=1000.0)
    first, _ = store.submit(request("first-key-1"), FREE)
    store.request_stop(first.job_id)
    with pytest.raises(LimitError, match="24 hours"):
        store.submit(request("second-key-1"), FREE)
    store.submit(request("second-key-1", max_runtime_seconds=400), FREE)
    clock.now += timedelta(days=1, seconds=1)
    store.submit(request("third-key-1", max_runtime_seconds=999), FREE)


def test_the_same_key_of_two_owners_makes_two_jobs(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first, _ = store.submit(request(), FREE)
    second, created = store.submit(request(owner="bob", max_epochs=9), FREE)
    assert created
    assert first.job_id != second.job_id


def test_a_list_can_hold_one_owner(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.submit(request(), FREE)
    store.submit(request(owner="bob"), FREE)
    assert [job.request.owner for job in store.jobs("bob")] == ["bob"]
    assert len(store.jobs()) == 2
    assert len(store.jobs(limit=1)) == 1


def test_a_queue_older_than_owners_gets_them_from_its_requests(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite"
    store = JobStore(path)
    job, _ = store.submit(request(), FREE)
    db = sqlite3.connect(path)
    db.execute("DROP INDEX jobs_owner")
    db.execute("ALTER TABLE jobs DROP COLUMN owner")
    db.commit()
    db.close()
    assert JobStore(path).owner_of(job.job_id) == "alice"


def test_an_unknown_job_has_no_owner(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        store_at(tmp_path).owner_of("job-000000000000")


def test_old_audit_rows_leave_after_the_retention_period(tmp_path: Path) -> None:
    clock = Clock()
    store = store_at(tmp_path, clock)
    store.audit("alice", "job_read", None, "allowed")
    clock.now += timedelta(days=89)
    store.audit("alice", "job_read", None, "allowed")
    assert store.prune_audit(90) == 0
    clock.now += timedelta(days=2)
    assert store.prune_audit(90) == 1
    assert len(store.audit_rows()) == 1


def test_audit_rows_filter_by_actor_and_page(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    for actor in ("alice", "bob", "alice"):
        store.audit(actor, "job_read", None, "allowed")
    assert len(store.audit_rows("alice")) == 2
    assert [row.seq for row in store.audit_rows(after=1, limit=1)] == [2]


def test_an_erasure_waits_for_jobs_at_work(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    job, _ = store.submit(request(), FREE)
    store.approve(job.job_id, "root")
    store.lease("worker", 1, 60)
    with pytest.raises(JobError, match="stop these jobs first"):
        store.erase("alice")
    assert store.owner_of(job.job_id) == "alice"


def test_an_erasure_leaves_other_owners_and_hides_the_approver(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    mine, _ = store.submit(request(), FREE)
    other, _ = store.submit(request(owner="bob"), FREE)
    store.approve(other.job_id, "alice")
    store.audit("alice", "job_read", mine.job_id, "allowed")
    done = store.erase("alice")
    assert done.jobs_erased == (mine.job_id,)
    assert done.audit_rows_anonymized == 1
    with pytest.raises(KeyError):
        store.get(mine.job_id)
    assert store.get(other.job_id).approved_by == "erased"
    assert store.logs(other.job_id)
    assert store.audit_rows()[0].actor == "erased"


def test_an_export_holds_the_owner_and_nobody_else(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    mine, _ = store.submit(request(), FREE)
    store.submit(request(owner="bob"), FREE)
    store.audit("alice", "job_read", mine.job_id, "allowed")
    store.audit("bob", "job_read", None, "allowed")
    found = store.export_of("alice")
    assert [item.job.job_id for item in found.jobs] == [mine.job_id]
    assert [row.actor for row in found.audit] == ["alice"]
    assert found.logs
    assert "browser" in found.note


def filled(root: Path) -> Path:
    data = root / "data"
    store = JobStore(data / "jobs" / "jobs.sqlite")
    job, _ = store.submit(request(), FREE)
    store.audit("alice", "job_read", job.job_id, "allowed")
    folder = data / "simulations" / job.job_id
    folder.mkdir(parents=True)
    (folder / "report.json").write_text('{"a": 1}', encoding="utf-8")
    (data / "jobs" / job.job_id).mkdir()
    (data / "jobs" / job.job_id / "last.pt").write_bytes(b"weights")
    return data


def test_a_backup_restores_to_the_same_state(tmp_path: Path) -> None:
    data = filled(tmp_path)
    target = tmp_path / "backup"
    made = backup.create(data, target, START)
    assert made.jobs == 1
    assert made.audit_rows == 1
    fresh = tmp_path / "fresh"
    backup.restore(target, fresh)
    original = JobStore(data / "jobs" / "jobs.sqlite")
    restored = JobStore(fresh / "jobs" / "jobs.sqlite")
    assert restored.jobs() == original.jobs()
    assert restored.audit_rows() == original.audit_rows()
    job_id = original.jobs()[0].job_id
    assert (fresh / "simulations" / job_id / "report.json").read_text(
        encoding="utf-8"
    ) == '{"a": 1}'
    assert (fresh / "jobs" / job_id / "last.pt").read_bytes() == b"weights"


def test_a_backup_of_a_queue_in_use_is_consistent(tmp_path: Path) -> None:
    data = filled(tmp_path)
    keeper = sqlite3.connect(data / "jobs" / "jobs.sqlite")
    keeper.execute("BEGIN")
    keeper.execute("INSERT INTO audit (at, actor, action, outcome) VALUES ('x', 'a', 'b', 'c')")
    made = backup.create(data, tmp_path / "backup", START)
    keeper.rollback()
    keeper.close()
    assert made.audit_rows == 1


def test_a_backup_never_replaces_another(tmp_path: Path) -> None:
    data = filled(tmp_path)
    backup.create(data, tmp_path / "backup", START)
    with pytest.raises(backup.BackupError, match="exists"):
        backup.create(data, tmp_path / "backup", START)


def test_a_backup_needs_a_queue(tmp_path: Path) -> None:
    with pytest.raises(backup.BackupError, match="no queue"):
        backup.create(tmp_path / "nothing", tmp_path / "backup", START)


def test_a_changed_file_fails_the_check(tmp_path: Path) -> None:
    data = filled(tmp_path)
    target = tmp_path / "backup"
    backup.create(data, target, START)
    job_id = JobStore(data / "jobs" / "jobs.sqlite").jobs()[0].job_id
    (target / "simulations" / job_id / "report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(backup.BackupError, match="SHA-256"):
        backup.verify(target)
    with pytest.raises(backup.BackupError):
        backup.restore(target, tmp_path / "fresh")
    assert not (tmp_path / "fresh").exists()


def test_a_missing_or_added_file_fails_the_check(tmp_path: Path) -> None:
    data = filled(tmp_path)
    target = tmp_path / "backup"
    backup.create(data, target, START)
    (target / "planted.py").write_text("print('hello')", encoding="utf-8")
    with pytest.raises(backup.BackupError, match="differ"):
        backup.verify(target)
    (target / "planted.py").unlink()
    (target / "jobs" / "jobs.sqlite").unlink()
    with pytest.raises(backup.BackupError, match="differ"):
        backup.verify(target)


def test_a_restore_overwrites_nothing(tmp_path: Path) -> None:
    data = filled(tmp_path)
    target = tmp_path / "backup"
    backup.create(data, target, START)
    with pytest.raises(backup.BackupError, match="empty folder"):
        backup.restore(target, data)


def test_a_folder_without_a_manifest_or_of_another_format_is_refused(tmp_path: Path) -> None:
    with pytest.raises(backup.BackupError, match="no manifest"):
        backup.verify(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"format": 99}), encoding="utf-8")
    with pytest.raises(backup.BackupError, match="format"):
        backup.verify(tmp_path)


def test_no_secret_file_goes_into_a_backup(tmp_path: Path) -> None:
    data = filled(tmp_path)
    (data / ".env").write_text("MULTIVERSE_FRED_API_KEY=x", encoding="utf-8")
    made = backup.create(data, tmp_path / "backup", START)
    assert not any(".env" in name for name in made.files)
    assert "jobs/jobs.sqlite" in made.files


@pytest.mark.parametrize(
    "hostile",
    ["' OR '1'='1", "job-000000000000'; DROP TABLE jobs; --", '" OR ""="', "%", "_"],
)
def test_text_from_a_request_stays_a_value_in_sql(tmp_path: Path, hostile: str) -> None:
    store = store_at(tmp_path)
    job, _ = store.submit(request(), FREE)
    with pytest.raises(KeyError):
        store.get(hostile)
    with pytest.raises(KeyError):
        store.owner_of(hostile)
    assert store.jobs(hostile) == []
    store.audit(hostile, "job_read", None, "denied")
    assert store.get(job.job_id).job_id == job.job_id
