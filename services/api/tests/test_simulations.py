"""Monte Carlo over HTTP: the API records a run and reads its report, it never simulates."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from multiverse_api.main import create_app
from multiverse_config import Settings
from multiverse_contracts.interventions import CATALOG


def decision() -> dict[str, Any]:
    spec = CATALOG.spec("debt_refinance")
    return {
        "type": "debt_refinance",
        "magnitude": {"value": "500000000", "unit": "usd"},
        "timing": {
            "announcement_date": "2026-07-01",
            "effective_date": "2026-10-01",
            "lag_quarters": 0,
            "ramp_quarters": 0,
        },
        "current_interest_rate": "0.05",
        "new_interest_rate": {"shape": "fixed", "value": "0.04"},
        "new_maturity_years": 5,
        "refinancing_fee_fraction": "0.01",
    } | ({"type": spec.type.value})


def body(**changes: Any) -> dict[str, Any]:
    return {
        "idempotency_key": "stage-22-api-run",
        "owner": "owner",
        "case_id": "case-synthetic-northwind",
        "decision": decision(),
        "settings": {"paths": 1000, "seed": 7},
        "max_runtime_seconds": 600,
    } | changes


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, env="test", data_dir=tmp_path)  # type: ignore[call-arg]
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8000")


def test_an_estimate_comes_before_any_run(client: TestClient) -> None:
    found = client.post("/api/v1/simulations/estimate", json=body()).json()
    assert found["seconds"] > 0
    assert "paths" in found["basis"]
    assert client.get("/api/v1/jobs").json() == []


def test_a_repeated_submit_gives_the_same_job(client: TestClient) -> None:
    first = client.post("/api/v1/simulations", json=body())
    second = client.post("/api/v1/simulations", json=body())
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["job_id"] == second.json()["job_id"]
    assert first.json()["status"] == "queued"
    other = body(settings={"paths": 2000, "seed": 7})
    assert client.post("/api/v1/simulations", json=other).status_code == 409


def test_a_run_is_a_job_like_any_other(client: TestClient) -> None:
    job_id = client.post("/api/v1/simulations", json=body()).json()["job_id"]
    listed = client.get("/api/v1/jobs").json()
    assert listed[0]["request"]["kind"] == "simulation"
    approved = client.post(f"/api/v1/jobs/{job_id}/approve").json()
    assert approved["approved_by"] == "owner"
    stopped = client.post(f"/api/v1/jobs/{job_id}/stop").json()
    assert stopped["status"] == "stopped"


def test_too_many_paths_are_refused(client: TestClient) -> None:
    found = client.post("/api/v1/simulations", json=body(settings={"paths": 200_000, "seed": 7}))
    assert found.status_code == 422


def test_a_report_is_there_only_when_a_worker_wrote_it(client: TestClient, tmp_path: Path) -> None:
    job_id = client.post("/api/v1/simulations", json=body()).json()["job_id"]
    assert client.get(f"/api/v1/simulations/{job_id}/report").status_code == 404
    assert client.get("/api/v1/simulations/job-000000000000/report").status_code == 404


def test_the_api_process_never_imports_the_simulator() -> None:
    import subprocess
    import sys

    code = "import sys, multiverse_api.main; print('multiverse_simulation' in sys.modules)"
    found = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert json.loads(found.stdout.strip().lower()) is False


def test_the_research_report_downloads_as_the_worker_wrote_it(
    client: TestClient, tmp_path: Path
) -> None:
    from multiverse_simulation.cli import run_case
    from multiverse_simulation.example import default_decision, illustrative_case
    from multiverse_simulation.reportdoc import write_report_files

    from multiverse_contracts.decisions import DECISION_MODELS
    from multiverse_contracts.simulation import SimulationSettings

    job_id = client.post("/api/v1/simulations", json=body()).json()["job_id"]
    url = f"/api/v1/simulations/{job_id}/report"
    assert client.get(f"{url}/markdown").status_code == 404
    case = illustrative_case(horizon=8, history_quarters=40)
    chosen = DECISION_MODELS["rnd_change"].model_validate_json(
        json.dumps(default_decision("rnd_change"))
    )
    report = run_case(case, chosen, SimulationSettings(paths=200, seed=5, batch_paths=100))  # type: ignore[arg-type]
    folder = tmp_path / "simulations" / job_id
    manifest = write_report_files(folder, report, case, chosen)  # type: ignore[arg-type]

    markdown = client.get(f"{url}/markdown")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    disposition = markdown.headers["content-disposition"]
    assert disposition == f'attachment; filename="{manifest.report_doc_id}.md"'
    assert markdown.content == (folder / "report.md").read_bytes()
    table = client.get(f"{url}/csv")
    assert table.headers["content-type"].startswith("text/csv")
    assert table.text.splitlines()[0] == "table,metric,scenario,period,statistic,value,unit"
    assert client.get(f"{url}/document").json()["report_doc_id"] == manifest.report_doc_id
    assert (
        client.get(f"{url}/manifest")
        .headers["content-disposition"]
        .endswith(f'{manifest.report_doc_id}-manifest.json"')
    )
    again = client.get(f"{url}/markdown")
    assert again.headers["etag"] == markdown.headers["etag"]
    assert client.get(f"{url}/pdf").status_code == 422
