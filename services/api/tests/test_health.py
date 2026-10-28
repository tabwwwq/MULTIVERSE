"""Smoke test of the API composition root."""

from fastapi.testclient import TestClient

from multiverse_api.main import create_app
from multiverse_config import Environment, Settings
from multiverse_contracts import CONTRACTS_VERSION


def _client(env: Environment) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, env=env)))


def test_health_reports_service_and_contracts_version() -> None:
    response = _client(Environment.TEST).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "multiverse-api",
        "version": "0.1.0",
        "environment": "test",
        "contracts_version": CONTRACTS_VERSION,
    }


def test_docs_are_hidden_in_production() -> None:
    client = _client(Environment.PRODUCTION)

    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 404
    assert client.get("/api/v1/health").status_code == 200
