"""Monte Carlo jobs: a batch of paths is the safe point, as an epoch is for a training.

The frame goes to disk after each batch. A stop, a pause or a killed process lose at most the
batch in hand, and a resumed run ends in the same numbers: each path has its own seed.
"""

from datetime import UTC, datetime
from pathlib import Path

from multiverse_simulation.run import Frame, ReconciliationBugError, simulate
from multiverse_simulation.summary import build_report

from multiverse_contracts.jobs import JobView
from multiverse_contracts.simulation import SimulationCase, SimulationRequest
from multiverse_worker.runner import Decision, RefusedError, Session, Trainer

CASES = Path("data/simulation")


def request_of(job: JobView) -> SimulationRequest:
    if not isinstance(job.request, SimulationRequest):
        raise RefusedError(f"{job.job_id} is not a simulation")
    return job.request


class SimulationRunner:
    def __init__(self, data_dir: Path, cases: Path = CASES, code_version: str = "worker") -> None:
        self.data_dir = data_dir
        self.cases = cases
        self.code_version = code_version

    def folder(self, job: JobView) -> Path:
        return self.data_dir / "simulations" / job.job_id

    def case(self, request: SimulationRequest) -> SimulationCase:
        path = self.cases / f"{request.case_id}.json"
        if not path.exists():
            raise RefusedError(f"no case {request.case_id}")
        return SimulationCase.model_validate_json(path.read_bytes())

    def validate(self, job: JobView) -> None:
        self.case(request_of(job))

    def run(self, job: JobView, session: Session) -> Decision:
        request = request_of(job)
        case = self.case(request)
        settings = request.settings
        folder = self.folder(job)
        checkpoint = folder / "frame.npz"
        frame = Frame.load(checkpoint) if checkpoint.exists() else None
        batches = 0

        def safe_point(current: Frame) -> Decision:
            nonlocal batches
            batches += 1
            sha256 = current.save(checkpoint)
            return session.after_batch(batches, current.done, settings.paths, sha256)

        try:
            finished, answer = simulate(
                case, request.decision, settings, frame=frame, on_batch=safe_point
            )
        except ReconciliationBugError as error:
            raise RefusedError(str(error)) from error
        if answer != "continue":
            return answer
        report = build_report(
            case,
            request.decision,
            settings,
            finished,
            code_version=self.code_version,
            created_at=datetime.now(UTC),
            seconds=session.elapsed,
        )
        pending = folder / "report.pending"
        pending.write_text(report.model_dump_json(), encoding="utf-8")
        pending.replace(folder / "report.json")
        session.reason = f"{settings.paths} paths, report {report.manifest.report_id}"
        return "continue"


class Dispatcher:
    """One queue, two kinds of work."""

    def __init__(self, training: Trainer, simulation: Trainer) -> None:
        self.training = training
        self.simulation = simulation

    def _for(self, job: JobView) -> Trainer:
        return self.simulation if isinstance(job.request, SimulationRequest) else self.training

    def validate(self, job: JobView) -> None:
        self._for(job).validate(job)

    def run(self, job: JobView, session: Session) -> Decision:
        return self._for(job).run(job, session)
