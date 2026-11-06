"""Long jobs over HTTP: the API records requests and reads state, it never trains or simulates.

Workers do the work (ADR-0003), however small a run is. A job needs an approved estimate before
any worker takes it, a repeated submit with the same key returns the same job, and stop and pause
wait for a safe point of the worker: an epoch, or a batch of paths.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from multiverse_config import Settings
from multiverse_contracts.jobs import JobDetail, JobEstimate, JobLogLine, JobRequest, JobView
from multiverse_contracts.simulation import SimulationReport, SimulationRequest
from multiverse_jobs.estimate import estimate
from multiverse_jobs.store import JobError, JobStore


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    by: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


async def job_request(request: Request) -> JobRequest:
    """Contracts are strict: JSON has lists where they hold tuples, so JSON is parsed as JSON."""
    try:
        return JobRequest.model_validate_json(await request.body())
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


async def simulation_request(request: Request) -> SimulationRequest:
    try:
        return SimulationRequest.model_validate_json(await request.body())
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


Submitted = Annotated[JobRequest, Depends(job_request)]
Simulation = Annotated[SimulationRequest, Depends(simulation_request)]


def store_of(settings: Settings) -> JobStore:
    return JobStore(Path(settings.data_dir) / "jobs" / "jobs.sqlite")


def build_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["jobs"])
    store = store_of(settings)

    def known(job_id: str) -> JobDetail:
        try:
            return store.detail(job_id)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job {job_id}") from error

    @router.post("/estimate")
    def estimate_job(request: Submitted) -> JobEstimate:
        return estimate(request)

    @router.post("", status_code=status.HTTP_201_CREATED)
    def submit(request: Submitted, response: Response) -> JobView:
        try:
            view, created = store.submit(request, estimate(request))
        except JobError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        if not created:
            response.status_code = status.HTTP_200_OK
        return view

    @router.get("")
    def jobs() -> list[JobView]:
        return store.jobs()

    @router.get("/{job_id}")
    def job(job_id: str) -> JobDetail:
        return known(job_id)

    @router.get("/{job_id}/logs")
    def logs(job_id: str, after: int = Query(default=0, ge=0)) -> list[JobLogLine]:
        known(job_id)
        return store.logs(job_id, after)

    def act(job_id: str, action: str, by: str | None = None) -> JobView:
        known(job_id)
        try:
            if action == "approve":
                return store.approve(job_id, by or "owner")
            if action == "pause":
                return store.request_pause(job_id)
            if action == "stop":
                return store.request_stop(job_id)
            return store.resume(job_id)
        except JobError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/{job_id}/approve")
    def approve(job_id: str, approval: Approval) -> JobView:
        return act(job_id, "approve", approval.by)

    @router.post("/{job_id}/pause")
    def pause(job_id: str) -> JobView:
        return act(job_id, "pause")

    @router.post("/{job_id}/stop")
    def stop(job_id: str) -> JobView:
        return act(job_id, "stop")

    @router.post("/{job_id}/resume")
    def resume(job_id: str) -> JobView:
        return act(job_id, "resume")

    return router


def build_simulation_router(settings: Settings) -> APIRouter:
    """Asked for here, run by a worker; approve, stop and resume are the routes of any job."""
    router = APIRouter(prefix="/simulations", tags=["simulations"])
    store = store_of(settings)

    @router.post("/estimate")
    def estimate_run(request: Simulation) -> JobEstimate:
        return estimate(request)

    @router.post("", status_code=status.HTTP_201_CREATED)
    def submit(request: Simulation, response: Response) -> JobView:
        try:
            view, created = store.submit(request, estimate(request))
        except JobError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        if not created:
            response.status_code = status.HTTP_200_OK
        return view

    @router.get("/{job_id}/report")
    def report(job_id: str) -> SimulationReport:
        try:
            store.get(job_id)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job {job_id}") from error
        path = Path(settings.data_dir) / "simulations" / job_id / "report.json"
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{job_id} has no report yet")
        return SimulationReport.model_validate_json(path.read_bytes())

    return router
