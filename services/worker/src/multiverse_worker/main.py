"""Composition root of the background worker.

Without arguments it only validates the configuration. ``run`` works through the queue and
exits when it is empty: no process keeps training, or waits to, unless asked with ``--watch``.

    multiverse-worker run
    multiverse-worker status
    multiverse-worker kill <job id> --yes
    multiverse-worker backup <folder>
    multiverse-worker verify <folder>
    multiverse-worker restore <folder> <data folder>
"""

import argparse
import logging
import os
import signal
import socket
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from multiverse_config import load_settings
from multiverse_contracts.jobs import JobRequest
from multiverse_jobs import backup
from multiverse_jobs.store import JobStore, Limits
from multiverse_worker.runner import RefusedError, work
from multiverse_worker.simulation import Dispatcher, SimulationRunner
from multiverse_worker.training import ForecastTrainer

log = logging.getLogger("multiverse_worker")
TTL_SECONDS = 60.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="multiverse-worker")
    commands = parser.add_subparsers(dest="command")
    run = commands.add_parser("run", help="work through the queue, then exit")
    run.add_argument("--watch", type=float, default=0.0, help="seconds to wait for new jobs")
    run.add_argument("--max-jobs", type=int)
    run.add_argument("--ttl", type=float, default=TTL_SECONDS, help="lease in seconds")
    commands.add_parser("status", help="every job and how it stands")
    commands.add_parser("reports", help="research reports of finished runs that lack them")
    kill = commands.add_parser("kill", help="end the process of a job without a safe point")
    kill.add_argument("job_id")
    kill.add_argument("--yes", action="store_true", help="accept losing the running epoch")
    copy = commands.add_parser(
        "backup", help="the queue and the files of its jobs, to a new folder"
    )
    copy.add_argument("folder", type=Path)
    check = commands.add_parser("verify", help="check a backup against its manifest")
    check.add_argument("folder", type=Path)
    back = commands.add_parser("restore", help="a backup into a folder without a queue")
    back.add_argument("folder", type=Path)
    back.add_argument("data_dir", type=Path)
    return parser


def _status(store: JobStore) -> int:
    for job in store.jobs():
        request = job.request
        step = (
            f"epoch {job.epoch}/{request.max_epochs}"
            if isinstance(request, JobRequest)
            else f"batch {job.epoch}, {request.settings.paths} paths"
        )
        print(
            f"{job.job_id} {job.status.value:<16} {job.progress_percent:5.1f}%  {step}"
            f"  {job.elapsed_seconds:.0f} s  {job.reason or ''}"
        )
    return 0


def _reports(store: JobStore, data_dir: Path) -> int:
    runner = SimulationRunner(data_dir)
    for job in store.jobs():
        if job.request.kind != "simulation" or job.status.value != "completed":
            continue
        try:
            made = runner.write_files(job)
        except RefusedError as error:
            print(f"{job.job_id}: {error}")
            continue
        print(f"{job.job_id}: {made or 'no report'}")
    return 0


def _kill(store: JobStore, job_id: str, yes: bool) -> int:
    job = store.get(job_id)
    pid = store.pid(job_id)
    if pid is None:
        print(f"{job_id} has no running process")
        return 1
    warning = f"The running epoch is lost: the job goes back to epoch {job.epoch} when resumed."
    if not yes:
        print(f"{warning} Use a stop for a safe point, or repeat with --yes.")
        return 1
    print(warning)
    os.kill(pid, signal.SIGTERM)
    store.log(job_id, "warning", f"process {pid} killed by the owner, no safe point")
    return 0


def _backup(args: argparse.Namespace, data_dir: Path) -> int:
    try:
        if args.command == "backup":
            made = backup.create(data_dir, args.folder, datetime.now(UTC))
        elif args.command == "verify":
            made = backup.verify(args.folder)
        else:
            made = backup.restore(args.folder, args.data_dir)
    except backup.BackupError as error:
        print(f"refused: {error}")
        return 1
    print(
        f"{args.command}: {len(made.files)} files, {made.jobs} jobs, {made.audit_rows} audit rows"
    )
    return 0


def main(argv: Sequence[str] = ()) -> int:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    if args.command is None:
        log.info("worker configured for profile %r", settings.env.value)
        return 0
    if args.command in ("verify", "restore"):
        return _backup(args, settings.data_dir)
    store = JobStore(
        settings.data_dir / "jobs" / "jobs.sqlite",
        limits=Limits(
            cloud_spend_usd=float(settings.cloud_spend_limit_usd),
            active_jobs=settings.max_active_jobs,
            daily_compute_seconds=settings.daily_compute_seconds,
        ),
    )
    if args.command == "backup":
        return _backup(args, settings.data_dir)
    if args.command == "status":
        return _status(store)
    if args.command == "reports":
        return _reports(store, settings.data_dir)
    if args.command == "kill":
        return _kill(store, args.job_id, args.yes)
    worker = f"{socket.gethostname()}-{os.getpid()}"
    trainer = Dispatcher(ForecastTrainer(settings.data_dir), SimulationRunner(settings.data_dir))
    count = work(store, trainer, worker, args.ttl, watch_seconds=args.watch, max_jobs=args.max_jobs)
    log.info("worker %s handled %d jobs", worker, count)
    return 0


def cli() -> int:
    return main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(cli())
