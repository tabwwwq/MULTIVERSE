"""Long jobs (Stages 18 and 22): what was asked, what it may cost, how it stands now.

A job is one training of a temporal model, or one Monte Carlo run, outside any HTTP request. It
starts only after its estimate was approved, survives the browser and the worker, and stops at
a safe point: an epoch or a batch of paths. The states are those of the prompt, plus a stop
that was asked for and not yet reached.
"""

import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints

from multiverse_contracts.forecasting import EpochLog, Name, Param, Score
from multiverse_contracts.normalized import Text
from multiverse_contracts.pit import Sha256
from multiverse_contracts.primitives import ContractModel
from multiverse_contracts.simulation import SimulationRequest

JobId = Annotated[str, StringConstraints(pattern=r"^job-[0-9a-f]{12}$")]


class JobStatus(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    STOP_REQUESTED = "stop_requested"
    STOPPED = "stopped"
    FAILED = "failed"
    COMPLETED = "completed"


class JobRequest(ContractModel):
    """Everything a job needs; a second submit with the same key returns the first job."""

    kind: Literal["training"] = "training"
    idempotency_key: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{8,80}$")]
    owner: Name
    model: Literal["gru_attention", "tcn"]
    params: tuple[Param, ...] = ()
    dataset_id: Annotated[str, StringConstraints(pattern=r"^fds-[0-9]{8}-[0-9a-f]{12}$")]
    dataset_sha256: Sha256
    protocol_path: str = Field(min_length=1, max_length=200)
    fold_year: int = Field(ge=2000, le=2100)
    seed: int
    device: Literal["auto", "cpu", "cuda"] = "auto"
    max_epochs: int = Field(ge=1, le=500)
    max_runtime_seconds: int = Field(ge=1, description="Over all attempts together.")
    spend_limit_usd: Score = Field(ge=0)
    rate_usd_per_hour: Score = Field(default=0, ge=0, description="Zero on the owner's own GPU.")
    overnight: bool = Field(
        default=False, description="Asked for on purpose: a job may run past the usual limit."
    )


AnyRequest = Annotated[JobRequest | SimulationRequest, Field(discriminator="kind")]


def parse_request(text: str | bytes) -> JobRequest | SimulationRequest:
    """Stored and submitted requests. Rows written before Stage 22 have no kind: they train."""
    if json.loads(text).get("kind") == "simulation":
        return SimulationRequest.model_validate_json(text)
    return JobRequest.model_validate_json(text)


class JobEstimate(ContractModel):
    """Shown before approval: measured rates, never a promise."""

    seconds: Score = Field(ge=0)
    vram_mb: Score = Field(ge=0)
    disk_mb: Score = Field(ge=0)
    cost_usd: Score = Field(ge=0)
    basis: Text


class JobLogLine(ContractModel):
    seq: int = Field(ge=1)
    at: AwareDatetime
    level: Literal["info", "warning", "error"]
    message: Text


class JobView(ContractModel):
    """The state of a job as the screen shows it; the store is the only source of it."""

    job_id: JobId
    request: AnyRequest
    estimate: JobEstimate
    status: JobStatus
    approved_by: Name | None = None
    approved_at: AwareDatetime | None = None
    attempt: int = Field(ge=0, description="Times a worker has taken the job.")
    max_attempts: int = Field(ge=1)
    epoch: int = Field(ge=0)
    best_epoch: int | None = None
    best_validation_loss: Score | None = None
    train_loss: Score | None = None
    validation_loss: Score | None = None
    batch_size: int = Field(ge=1)
    progress_percent: Score = Field(
        ge=0,
        le=100,
        description="Epochs or paths over the maximum; early stopping jumps to 100.",
    )
    elapsed_seconds: Score = Field(ge=0, description="Over all attempts together.")
    spent_usd: Score = Field(ge=0)
    last_heartbeat: AwareDatetime | None = None
    worker: str | None = None
    reason: Text | None = None
    alerts: tuple[Text, ...] = ()
    checkpoint_sha256: Sha256 | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class JobDetail(ContractModel):
    job: JobView
    metrics: tuple[EpochLog, ...] = ()
