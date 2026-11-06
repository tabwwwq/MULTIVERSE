"""Composition root of the background worker.

Without arguments it only validates the configuration. ``run`` works through the queue and
exits when it is empty: no process keeps training, or waits to, unless asked with ``--watch``.

    multiverse-worker run
    multiverse-worker status
    multiverse-worker kill <job id> --yes
"""

import argparse
import logging
import os
import signal
import socket
import sys
from collections.abc import Sequence

from multiverse_config import load_settings
from multiverse_contracts.jobs import JobRequest
from multiverse_jobs.store import JobStore
from multiverse_worker.runner import work
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
    kill = commands.add_parser("kill", help="end the process of a job without a safe point")
    kill.add_argument("job_id")
    kill.add_argument("--yes", action="store_true", help="accept losing the running epoch")
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


def main(argv: Sequence[str] = ()) -> int:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    if args.command is None:
        log.info("worker configured for profile %r", settings.env.value)
        return 0
    store = JobStore(settings.data_dir / "jobs" / "jobs.sqlite")
    if args.command == "status":
        return _status(store)
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
