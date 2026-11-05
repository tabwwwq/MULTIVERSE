"""Composition root of the HTTP API.

All wiring happens here: settings are loaded and validated once, then passed to the
routers that need them. No other API module reads environment variables.

Run locally: ``npm run dev:api``.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from multiverse_api import __version__
from multiverse_api.routes import health, jobs
from multiverse_config import Environment, Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. Tests pass explicit settings; production reads the environment."""
    settings = settings if settings is not None else load_settings()
    is_production = settings.env is Environment.PRODUCTION

    app = FastAPI(
        title="MULTIVERSE API",
        version=__version__,
        openapi_url=None if is_production else "/api/v1/openapi.json",
        docs_url=None if is_production else "/api/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.web_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.build_router(settings), prefix="/api/v1")
    app.include_router(jobs.build_router(settings), prefix="/api/v1")
    return app
