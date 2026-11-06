"""Smoke test of the API composition root."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from multiverse_api.main import create_app
from multiverse_config import ApiPrincipal, Environment, Role, Settings
from multiverse_contracts import CONTRACTS_VERSION

LOOPBACK = "http://127.0.0.1:8000"


def _client(env: Environment, tmp_path: Path) -> TestClient:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env=env,
        data_dir=tmp_path,
        auth_mode="local" if env is Environment.TEST else "token",
        api_principals=()
        if env is Environment.TEST
        else (
            ApiPrincipal(
                name="admin",
                role=Role.ADMIN,
                token_sha256="ab" * 32,
                expires_at=datetime(2030, 1, 1, tzinfo=UTC),
            ),
        ),
    )
    return TestClient(create_app(settings), base_url=LOOPBACK)


def test_health_reports_service_and_contracts_version(tmp_path: Path) -> None:
    response = _client(Environment.TEST, tmp_path).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "multiverse-api",
        "version": "0.1.0",
        "environment": "test",
        "contracts_version": CONTRACTS_VERSION,
    }


def test_docs_are_hidden_in_production(tmp_path: Path) -> None:
    client = _client(Environment.PRODUCTION, tmp_path)

    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 404
    assert client.get("/api/v1/health").status_code == 200
