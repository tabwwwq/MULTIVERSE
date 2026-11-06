"""What the server holds about an account, and the way to take it away (GDPR art. 15, 17, 20).

The audit log is readable by an admin only. An erasure needs the name typed back: there is no
undo, and it removes the files of the jobs too.
"""

import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from multiverse_api.security import Access, Principal
from multiverse_config import Role, Settings
from multiverse_contracts.jobs import AccountExport, AuditRow, Erasure
from multiverse_jobs.store import ERASED, JobError, JobStore

JOB_FOLDERS = ("jobs", "simulations")


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    role: Role


class EraseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    confirm: str = Field(min_length=1, max_length=40, description="The name of this account.")


def build_router(settings: Settings, store: JobStore, access: Access) -> APIRouter:
    router = APIRouter(tags=["account"])

    @router.get("/me")
    def me(
        principal: Annotated[Principal, Depends(access.as_(Role.VIEWER, "account_read"))],
    ) -> Identity:
        store.audit(principal.name, "account_read", None, "allowed")
        return Identity(name=principal.name, role=principal.role)

    @router.get("/me/export")
    def export(
        principal: Annotated[Principal, Depends(access.as_(Role.VIEWER, "account_export"))],
    ) -> AccountExport:
        store.audit(principal.name, "account_export", None, "allowed")
        return store.export_of(principal.name)

    @router.post("/me/erase")
    def erase(
        request: EraseRequest,
        principal: Annotated[Principal, Depends(access.as_(Role.VIEWER, "account_erase"))],
    ) -> Erasure:
        if request.confirm != principal.name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirm with the account name")
        try:
            erased = store.erase(principal.name)
        except JobError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        for job_id in erased.jobs_erased:
            for folder in JOB_FOLDERS:
                shutil.rmtree(Path(settings.data_dir) / folder / job_id, ignore_errors=True)
        store.audit(ERASED, "account_erase", None, "allowed")
        return erased

    @router.get("/audit")
    def audit(
        principal: Annotated[Principal, Depends(access.as_(Role.ADMIN, "audit_read"))],
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> list[AuditRow]:
        store.audit(principal.name, "audit_read", None, "allowed")
        return store.audit_rows(after=after, limit=limit)

    return router
