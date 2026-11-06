"""Training jobs over HTTP: requests are recorded, nothing trains here."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from multiverse_api.main import create_app
from multiverse_config import Settings

SHA = "ab" * 32


def body(**changes: Any) -> dict[str, Any]:
    return {
        "idempotency_key": "stage-18-test-run",
        "owner": "owner",
        "model": "gru_attention",
        "dataset_id": f"fds-20261028-{SHA[:12]}",
        "dataset_sha256": SHA,
        "protocol_path": "data/protocols/stage-16-temporal-large.json",
        "params": [{"name": "hidden", "value": "64"}],
        "fold_year": 2026,
        "seed": 1,
        "max_epochs": 10,
        "max_runtime_seconds": 600,
        "spend_limit_usd": 0,
    } | changes


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, env="test", data_dir=tmp_path)  # type: ignore[call-arg]
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8000")


def test_an_estimate_comes_before_any_job(client: TestClient) -> None:
    found = client.post("/api/v1/jobs/estimate", json=body()).json()
    assert found["seconds"] > 0
    assert "measured" in found["basis"]
    assert client.get("/api/v1/jobs").json() == []


def test_a_repeated_submit_gives_the_same_job(client: TestClient) -> None:
    first = client.post("/api/v1/jobs", json=body())
    second = client.post("/api/v1/jobs", json=body())
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["job_id"] == second.json()["job_id"]
    assert first.json()["status"] == "queued"
    assert first.json()["approved_at"] is None
    assert client.post("/api/v1/jobs", json=body(max_epochs=11)).status_code == 409


def test_the_requests_of_a_job_are_recorded(client: TestClient) -> None:
    job_id = client.post("/api/v1/jobs", json=body()).json()["job_id"]
    approved = client.post(f"/api/v1/jobs/{job_id}/approve").json()
    assert approved["approved_by"] == "owner"
    stopped = client.post(f"/api/v1/jobs/{job_id}/stop").json()
    assert stopped["status"] == "stopped"
    assert client.post(f"/api/v1/jobs/{job_id}/pause").status_code == 409
    assert client.post(f"/api/v1/jobs/{job_id}/resume").json()["status"] == "queued"
    detail = client.get(f"/api/v1/jobs/{job_id}").json()
    assert detail["job"]["job_id"] == job_id
    assert detail["metrics"] == []
    lines = client.get(f"/api/v1/jobs/{job_id}/logs").json()
    assert lines[0]["message"].startswith("submitted by owner")
    after = client.get(f"/api/v1/jobs/{job_id}/logs", params={"after": lines[-1]["seq"]}).json()
    assert after == []


def test_an_unknown_job_and_a_bad_request_are_refused(client: TestClient) -> None:
    assert client.get("/api/v1/jobs/job-000000000000").status_code == 404
    assert client.post("/api/v1/jobs/job-000000000000/stop").status_code == 404
    assert client.post("/api/v1/jobs", json=body(max_epochs=0)).status_code == 422
    long = body(max_runtime_seconds=999_999)
    assert client.post("/api/v1/jobs", json=long).status_code == 409


def test_the_web_app_may_read_the_jobs(client: TestClient) -> None:
    answer = client.get("/api/v1/jobs", headers={"Origin": "http://localhost:3000"})
    assert answer.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = client.get("/api/v1/jobs", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in other.headers
