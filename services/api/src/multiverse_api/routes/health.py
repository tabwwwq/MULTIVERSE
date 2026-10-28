"""Liveness endpoint: proves the service started with a valid configuration."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from multiverse_api import __version__
from multiverse_config import Settings
from multiverse_contracts import CONTRACTS_VERSION


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"]
    service: str
    version: str
    environment: str
    contracts_version: str


def build_router(settings: Settings) -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="multiverse-api",
            version=__version__,
            environment=settings.env.value,
            contracts_version=CONTRACTS_VERSION,
        )

    return router
