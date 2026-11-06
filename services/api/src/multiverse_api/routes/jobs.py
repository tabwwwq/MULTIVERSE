"""Long jobs over HTTP: the API records requests and reads state, it never trains or simulates.

Workers do the work (ADR-0003), however small a run is. A job needs an approved estimate before
any worker takes it, a repeated submit with the same key returns the same job, and stop and pause
wait for a safe point of the worker: an epoch, or a batch of paths.

Every route names the role it needs. A job belongs to whoever submitted it, and only an admin
approves an estimate: what a run may cost is the one decision an operator cannot make alone.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from multiverse_api.security import Access, Principal
from multiverse_config import Role, Settings
from multiverse_contracts.jobs import JobDetail, JobEstimate, JobLogLine, JobRequest, JobView
from multiverse_contracts.simulation import SimulationReport, SimulationRequest
from multiverse_jobs.estimate import estimate
from multiverse_jobs.store import JobError, JobStore, LimitError, Limits


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
    return JobStore(
        Path(settings.data_dir) / "jobs" / "jobs.sqlite",
        limits=Limits(
            cloud_spend_usd=float(settings.cloud_spend_limit_usd),
            active_jobs=settings.max_active_jobs,
            daily_compute_seconds=settings.daily_compute_seconds,
        ),
    )


def enqueue(
    store: JobStore,
    principal: Principal,
    request: JobRequest | SimulationRequest,
    response: Response,
    action: str,
) -> JobView:
    """A job is owned by whoever asks for it, whatever name the body gives."""
    if request.owner != principal.name:
        store.audit(principal.name, action, None, "denied")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "a job belongs to whoever submits it")
    try:
        view, created = store.submit(request, estimate(request))
    except LimitError as error:
        store.audit(principal.name, action, None, "limited")
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from error
    except JobError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    store.audit(principal.name, action, view.job_id, "allowed")
    if not created:
        response.status_code = status.HTTP_200_OK
    return view


def build_router(store: JobStore, access: Access) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["jobs"])

    @router.post("/estimate")
    def estimate_job(
        _: Annotated[Principal, Depends(access.as_(Role.VIEWER, "job_estimate"))],
        request: Submitted,
    ) -> JobEstimate:
        return estimate(request)

    @router.post("", status_code=status.HTTP_201_CREATED)
    def submit(
        principal: Annotated[Principal, Depends(access.as_(Role.OPERATOR, "job_submit"))],
        request: Submitted,
        response: Response,
    ) -> JobView:
        return enqueue(store, principal, request, response, "job_submit")

    @router.get("")
    def jobs(
        principal: Annotated[Principal, Depends(access.as_(Role.VIEWER, "job_list"))],
    ) -> list[JobView]:
        store.audit(principal.name, "job_list", None, "allowed")
        return store.jobs(None if principal.role is Role.ADMIN else principal.name)

    @router.get("/{job_id}")
    def job(
        job_id: str,
        principal: Annotated[Principal, Depends(access.as_(Role.VIEWER, "job_read"))],
    ) -> JobDetail:
        access.owned(principal, job_id, "job_read")
        return store.detail(job_id)

    @router.get("/{job_id}/logs")
    def logs(
        job_id: str,
        principal: Annotated[Principal, Depends(access.as_(Role.VIEWER, "job_logs"))],
        after: int = Query(default=0, ge=0),
    ) -> list[JobLogLine]:
        access.owned(principal, job_id, "job_logs")
        return store.logs(job_id, after)

    def act(job_id: str, action: str, principal: Principal) -> JobView:
        access.owned(principal, job_id, f"job_{action}")
        try:
            if action == "approve":
                return store.approve(job_id, principal.name)
            if action == "pause":
                return store.request_pause(job_id)
            if action == "stop":
                return store.request_stop(job_id)
            return store.resume(job_id)
        except LimitError as error:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from error
        except JobError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @router.post("/{job_id}/approve")
    def approve(
        job_id: str, principal: Annotated[Principal, Depends(access.as_(Role.ADMIN, "job_approve"))]
    ) -> JobView:
        return act(job_id, "approve", principal)

    @router.post("/{job_id}/pause")
    def pause(
        job_id: str,
        principal: Annotated[Principal, Depends(access.as_(Role.OPERATOR, "job_pause"))],
    ) -> JobView:
        return act(job_id, "pause", principal)

    @router.post("/{job_id}/stop")
    def stop(
        job_id: str, principal: Annotated[Principal, Depends(access.as_(Role.OPERATOR, "job_stop"))]
    ) -> JobView:
        return act(job_id, "stop", principal)

    @router.post("/{job_id}/resume")
    def resume(
        job_id: str,
        principal: Annotated[Principal, Depends(access.as_(Role.OPERATOR, "job_resume"))],
    ) -> JobView:
        return act(job_id, "resume", principal)

    return router


def build_simulation_router(settings: Settings, store: JobStore, access: Access) -> APIRouter:
    """Asked for here, run by a worker; approve, stop and resume are the routes of any job."""
    router = APIRouter(prefix="/simulations", tags=["simulations"])

    @router.post("/estimate")
    def estimate_run(
        _: Annotated[Principal, Depends(access.as_(Role.VIEWER, "simulation_estimate"))],
        request: Simulation,
    ) -> JobEstimate:
        return estimate(request)

    @router.post("", status_code=status.HTTP_201_CREATED)
    def submit(
        principal: Annotated[Principal, Depends(access.as_(Role.OPERATOR, "simulation_submit"))],
        request: Simulation,
        response: Response,
    ) -> JobView:
        return enqueue(store, principal, request, response, "simulation_submit")

    @router.get("/{job_id}/report")
    def report(
        job_id: str,
        principal: Annotated[Principal, Depends(access.as_(Role.VIEWER, "simulation_report"))],
    ) -> SimulationReport:
        access.owned(principal, job_id, "simulation_report")
        path = Path(settings.data_dir) / "simulations" / job_id / "report.json"
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{job_id} has no report yet")
        return SimulationReport.model_validate_json(path.read_bytes())

    return router
