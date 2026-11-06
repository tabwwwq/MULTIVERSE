"""The boundary of the API, attacked the way the threat model says (Stage 24, ADR-0032)."""

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from multiverse_api.main import create_app
from multiverse_api.security import RateLimiter, host_of
from multiverse_api.tokens import entry, main, new_token
from multiverse_config import ApiPrincipal, Role, Settings

SHA = "ab" * 32
LOOPBACK = "http://127.0.0.1:8000"
LATER = datetime(2030, 1, 1, tzinfo=UTC)
TOKENS = {name: f"mv_test_token_of_{name}" for name in ("alice", "bob", "root", "guest", "old")}
PUBLIC = {"/api/v1/health", "/api/v1/openapi.json", "/api/docs", "/api/docs/oauth2-redirect"}
SIMPLE_POST = {"Content-Type": "text/plain"}


def principal(name: str, role: Role, expires_at: datetime = LATER) -> ApiPrincipal:
    digest = hashlib.sha256(TOKENS[name].encode()).hexdigest()
    return ApiPrincipal(name=name, role=role, token_sha256=digest, expires_at=expires_at)


def settings_for(tmp_path: Path, **changes: Any) -> Settings:
    values: dict[str, Any] = {
        "env": "test",
        "data_dir": tmp_path,
        "auth_mode": "token",
        "api_principals": (
            principal("alice", Role.OPERATOR),
            principal("bob", Role.OPERATOR),
            principal("root", Role.ADMIN),
            principal("guest", Role.VIEWER),
            principal("old", Role.ADMIN, datetime(2020, 1, 1, tzinfo=UTC)),
        ),
        "rate_failures_per_minute": 1000,
    } | changes
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def body(owner: str = "alice", **changes: Any) -> dict[str, Any]:
    return {
        "idempotency_key": "stage-24-test-run",
        "owner": owner,
        "model": "gru_attention",
        "dataset_id": f"fds-20261028-{SHA[:12]}",
        "dataset_sha256": SHA,
        "protocol_path": "data/protocols/stage-16-temporal-large.json",
        "fold_year": 2026,
        "seed": 1,
        "max_epochs": 10,
        "max_runtime_seconds": 600,
        "spend_limit_usd": 0,
    } | changes


def bearer(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[name]}"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(settings_for(tmp_path)), base_url=LOOPBACK) as found:
        yield found


@pytest.fixture
def alices_job(client: TestClient) -> str:
    answer = client.post("/api/v1/jobs", json=body(), headers=bearer("alice"))
    assert answer.status_code == 201
    job_id: str = answer.json()["job_id"]
    return job_id


def routes(client: TestClient) -> list[tuple[str, str]]:
    """From the app itself: a route added later is in this list without anyone adding it."""
    app: Any = client.app
    paths: dict[str, dict[str, object]] = app.openapi()["paths"]
    return sorted(
        (method.upper(), path)
        for path, item in paths.items()
        if path not in PUBLIC
        for method in item
    )


def test_the_route_list_is_not_empty(client: TestClient) -> None:
    assert len(routes(client)) >= 16


def test_no_route_answers_without_a_token(client: TestClient) -> None:
    for method, path in routes(client):
        url = path.replace("{job_id}", "job-000000000000")
        answer = client.request(method, url, headers={"Content-Type": "application/json"})
        assert answer.status_code == 401, (method, path)
        assert answer.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["Bearer wrong", "Bearer ", "Basic YWxpY2U6c2VjcmV0", f"bearer{TOKENS['alice']}", ""],
)
def test_a_bad_token_is_a_401(client: TestClient, header: str) -> None:
    assert client.get("/api/v1/jobs", headers={"Authorization": header}).status_code == 401


def test_an_expired_token_is_a_401(client: TestClient) -> None:
    assert client.get("/api/v1/jobs", headers=bearer("old")).status_code == 401


def test_a_token_stops_at_the_moment_it_expires(tmp_path: Path) -> None:
    moment = datetime(2030, 1, 1, tzinfo=UTC)
    settings = settings_for(tmp_path, api_principals=(principal("alice", Role.VIEWER, moment),))
    client = TestClient(create_app(settings), base_url=LOOPBACK)
    app: Any = client.app
    app.state.access.clock = lambda: moment - timedelta(seconds=1)
    assert client.get("/api/v1/me", headers=bearer("alice")).status_code == 200
    app.state.access.clock = lambda: moment
    assert client.get("/api/v1/me", headers=bearer("alice")).status_code == 401


def test_a_principal_knows_itself(client: TestClient) -> None:
    assert client.get("/api/v1/me", headers=bearer("alice")).json() == {
        "name": "alice",
        "role": "operator",
    }


def test_a_viewer_reads_and_changes_nothing(client: TestClient) -> None:
    assert client.get("/api/v1/jobs", headers=bearer("guest")).status_code == 200
    answer = client.post("/api/v1/jobs", json=body("guest"), headers=bearer("guest"))
    assert answer.status_code == 403


def test_nobody_submits_in_the_name_of_someone_else(client: TestClient) -> None:
    answer = client.post("/api/v1/jobs", json=body("bob"), headers=bearer("alice"))
    assert answer.status_code == 403
    assert client.get("/api/v1/jobs", headers=bearer("root")).json() == []


def test_only_an_admin_approves(client: TestClient, alices_job: str) -> None:
    url = f"/api/v1/jobs/{alices_job}/approve"
    assert client.post(url, headers=bearer("alice")).status_code == 403
    assert client.post(url, headers=bearer("bob")).status_code == 403
    answer = client.post(url, headers=bearer("root"))
    assert answer.status_code == 200
    assert answer.json()["approved_by"] == "root"


def test_an_approval_cannot_borrow_a_name(client: TestClient, alices_job: str) -> None:
    url = f"/api/v1/jobs/{alices_job}/approve"
    answer = client.post(url, json={"by": "somebody"}, headers=bearer("root"))
    assert answer.json()["approved_by"] == "root"


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("GET", ""),
        ("GET", "/logs"),
        ("POST", "/stop"),
        ("POST", "/pause"),
        ("POST", "/resume"),
    ],
)
def test_someone_elses_job_does_not_exist(
    client: TestClient, alices_job: str, method: str, suffix: str
) -> None:
    mine = client.request(method, f"/api/v1/jobs/{alices_job}{suffix}", headers=bearer("bob"))
    none = client.request(method, f"/api/v1/jobs/job-000000000000{suffix}", headers=bearer("bob"))
    assert mine.status_code == none.status_code == 404
    assert mine.json()["detail"].replace(alices_job, "x") == none.json()["detail"].replace(
        "job-000000000000", "x"
    )


def test_someone_elses_report_does_not_exist(client: TestClient, alices_job: str) -> None:
    url = f"/api/v1/simulations/{alices_job}/report"
    assert client.get(url, headers=bearer("bob")).json()["detail"] == f"no job {alices_job}"
    assert "no report yet" in client.get(url, headers=bearer("alice")).json()["detail"]


def test_a_list_holds_only_the_jobs_of_its_reader(client: TestClient, alices_job: str) -> None:
    assert client.get("/api/v1/jobs", headers=bearer("bob")).json() == []
    found = client.get("/api/v1/jobs", headers=bearer("alice")).json()
    assert [job["job_id"] for job in found] == [alices_job]
    assert len(client.get("/api/v1/jobs", headers=bearer("root")).json()) == 1


def test_an_admin_reads_the_job_of_anyone(client: TestClient, alices_job: str) -> None:
    assert client.get(f"/api/v1/jobs/{alices_job}", headers=bearer("root")).status_code == 200


def test_the_same_key_of_two_owners_is_two_jobs(client: TestClient, alices_job: str) -> None:
    answer = client.post("/api/v1/jobs", json=body("bob"), headers=bearer("bob"))
    assert answer.status_code == 201
    assert answer.json()["job_id"] != alices_job


def test_a_key_tells_nothing_about_another_owner(client: TestClient, alices_job: str) -> None:
    other = body("bob", max_epochs=99)
    assert client.post("/api/v1/jobs", json=other, headers=bearer("bob")).status_code == 201


def test_the_audit_log_holds_reads_and_refusals(client: TestClient, alices_job: str) -> None:
    client.get(f"/api/v1/jobs/{alices_job}", headers=bearer("alice"))
    client.get(f"/api/v1/jobs/{alices_job}", headers=bearer("bob"))
    client.get("/api/v1/jobs", headers={"Authorization": "Bearer wrong"})
    rows = client.get("/api/v1/audit", headers=bearer("root")).json()
    seen = {(r["actor"], r["action"], r["job_id"], r["outcome"]) for r in rows}
    assert ("alice", "job_submit", alices_job, "allowed") in seen
    assert ("alice", "job_read", alices_job, "allowed") in seen
    assert ("bob", "job_read", None, "not_found") in seen
    assert ("anonymous", "job_list", None, "denied") in seen


def test_the_audit_log_is_for_admins(client: TestClient) -> None:
    assert client.get("/api/v1/audit", headers=bearer("alice")).status_code == 403


def test_the_audit_log_holds_no_token_and_no_address(client: TestClient, alices_job: str) -> None:
    text = client.get("/api/v1/audit", headers=bearer("root")).text
    assert TOKENS["alice"] not in text
    assert "testclient" not in text
    assert "127.0.0.1" not in text


def test_an_account_exports_what_the_server_holds(client: TestClient, alices_job: str) -> None:
    found = client.get("/api/v1/me/export", headers=bearer("alice")).json()
    assert found["principal"] == "alice"
    assert [item["job"]["job_id"] for item in found["jobs"]] == [alices_job]
    assert found["logs"]
    assert {row["actor"] for row in found["audit"]} == {"alice"}
    other = client.get("/api/v1/me/export", headers=bearer("bob")).json()
    assert other["jobs"] == []


def test_an_erasure_needs_the_name_typed_back(client: TestClient, alices_job: str) -> None:
    url = "/api/v1/me/erase"
    answer = client.post(url, json={"confirm": "bob"}, headers=bearer("alice"))
    assert answer.status_code == 400
    assert client.get(f"/api/v1/jobs/{alices_job}", headers=bearer("alice")).status_code == 200


def test_an_erasure_takes_the_jobs_their_files_and_the_name(
    client: TestClient, alices_job: str, tmp_path: Path
) -> None:
    folder = tmp_path / "simulations" / alices_job
    folder.mkdir(parents=True)
    (folder / "report.json").write_text("{}", encoding="utf-8")
    kept = tmp_path / "simulations" / "job-111111111111"
    kept.mkdir()
    answer = client.post("/api/v1/me/erase", json={"confirm": "alice"}, headers=bearer("alice"))
    assert answer.status_code == 200
    assert answer.json()["jobs_erased"] == [alices_job]
    assert not folder.exists()
    assert kept.exists()
    assert client.get("/api/v1/jobs", headers=bearer("root")).json() == []
    rows = client.get("/api/v1/audit", headers=bearer("root")).json()
    assert "alice" not in {row["actor"] for row in rows}
    assert "erased" in {row["actor"] for row in rows}


def test_a_stranger_host_is_turned_away(client: TestClient) -> None:
    answer = client.get("/api/v1/health", headers={"Host": "evil.example"})
    assert answer.status_code == 400


@pytest.mark.parametrize(
    ("header", "name"),
    [
        ("127.0.0.1:8000", "127.0.0.1"),
        ("LOCALHOST", "localhost"),
        ("[::1]:8000", "::1"),
        ("evil.example:8000", "evil.example"),
    ],
)
def test_the_name_in_a_host_header(header: str, name: str) -> None:
    assert host_of(header) == name


def test_a_page_of_another_site_cannot_post(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_for(tmp_path, auth_mode="local", api_principals=())))
    client.base_url = LOOPBACK  # type: ignore[assignment]
    cross = {"Origin": "https://evil.example"}
    assert client.post("/api/v1/jobs", json=body("owner"), headers=cross).status_code == 403
    fetched = {"Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/v1/jobs", json=body("owner"), headers=fetched).status_code == 403
    assert client.post("/api/v1/jobs/job-000000000000/stop", headers=cross).status_code == 403
    null = {"Origin": "null"}
    assert client.post("/api/v1/jobs", json=body("owner"), headers=null).status_code == 403


def test_the_web_app_may_post(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_for(tmp_path, auth_mode="local", api_principals=())),
        base_url=LOOPBACK,
    )
    own = {"Origin": "http://localhost:3000"}
    assert client.post("/api/v1/jobs", json=body("owner"), headers=own).status_code == 201


def test_a_simple_form_post_is_refused(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_for(tmp_path, auth_mode="local", api_principals=())),
        base_url=LOOPBACK,
    )
    answer = client.post("/api/v1/jobs", content='{"owner":"owner"}', headers=SIMPLE_POST)
    assert answer.status_code == 415
    assert client.get("/api/v1/jobs").json() == []


def test_a_large_body_is_refused_before_it_is_read(client: TestClient) -> None:
    answer = client.post(
        "/api/v1/jobs",
        content=b"x" * 300_000,
        headers={"Content-Type": "application/json", **bearer("alice")},
    )
    assert answer.status_code == 413


def test_a_large_body_without_a_length_is_cut_off(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(100):
            yield b"x" * 10_000

    answer = client.post(
        "/api/v1/jobs",
        content=chunks(),
        headers={"Content-Type": "application/json", **bearer("alice")},
    )
    assert answer.status_code == 413


def test_a_length_that_is_not_a_number_is_refused(client: TestClient) -> None:
    headers = {"Content-Type": "application/json", "Content-Length": "-1"}
    assert client.post("/api/v1/jobs", content=b"", headers=headers).status_code == 413


def test_answers_carry_the_protective_headers(client: TestClient) -> None:
    headers = client.get("/api/v1/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store"
    assert headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in headers["content-security-policy"]
    refused = client.get("/api/v1/health", headers={"Host": "evil.example"}).headers
    assert refused["x-content-type-options"] == "nosniff"


def test_too_many_reads_wait(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_for(tmp_path, rate_reads_per_minute=3)), base_url=LOOPBACK
    )
    codes = [client.get("/api/v1/me", headers=bearer("alice")).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    answer = client.get("/api/v1/me", headers=bearer("alice"))
    assert int(answer.headers["retry-after"]) >= 1
    assert client.get("/api/v1/me", headers=bearer("bob")).status_code == 200


def test_too_many_writes_wait(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_for(tmp_path, rate_writes_per_minute=1)), base_url=LOOPBACK
    )
    first = client.post("/api/v1/jobs", json=body(), headers=bearer("alice"))
    assert first.status_code == 201
    again = client.post("/api/v1/jobs", json=body(), headers=bearer("alice"))
    assert again.status_code == 429
    assert client.get("/api/v1/jobs", headers=bearer("alice")).status_code == 200


def test_guessing_tokens_stops_after_a_few_tries(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_for(tmp_path, rate_failures_per_minute=3)), base_url=LOOPBACK
    )
    wrong = {"Authorization": "Bearer wrong"}
    codes = [client.get("/api/v1/jobs", headers=wrong).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    assert client.get("/api/v1/jobs", headers=bearer("alice")).status_code == 429


def test_a_good_token_does_not_count_as_a_failure(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_for(tmp_path, rate_failures_per_minute=1)), base_url=LOOPBACK
    )
    codes = [client.get("/api/v1/me", headers=bearer("alice")).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 200]


def test_the_window_of_the_limiter_moves_on() -> None:
    now = [0.0]
    limiter = RateLimiter(lambda: now[0])
    assert limiter.allow("key", 1) is None
    assert limiter.allow("key", 1) == 60
    now[0] = 59.0
    assert limiter.allow("key", 1) == 1
    now[0] = 60.0
    assert limiter.allow("key", 1) is None


def test_a_limiter_forgets_those_who_left() -> None:
    now = [0.0]
    limiter = RateLimiter(lambda: now[0])
    limiter.hit("key")
    now[0] = 61.0
    assert limiter.wait("key", 5) is None
    assert limiter.hits == {}


def test_a_paid_job_is_refused_while_the_cloud_limit_is_zero(client: TestClient) -> None:
    paid = body(rate_usd_per_hour=100, spend_limit_usd=1000, max_runtime_seconds=3600)
    answer = client.post("/api/v1/jobs", json=paid, headers=bearer("alice"))
    assert answer.status_code == 429
    assert "paid compute is off" in answer.json()["detail"]


def test_a_flood_of_jobs_stops_at_the_limit_of_active_jobs(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_for(tmp_path, max_active_jobs=2)), base_url=LOOPBACK)
    keys = [f"flood-key-{n:04d}" for n in range(4)]
    codes = [
        client.post(
            "/api/v1/jobs", json=body(idempotency_key=key), headers=bearer("alice")
        ).status_code
        for key in keys
    ]
    assert codes == [201, 201, 429, 429]


def test_a_path_outside_the_protocols_is_a_422(client: TestClient) -> None:
    for path in ("../../.env", "/etc/passwd", "data/protocols/../../.env", "C:\\Windows\\x.json"):
        answer = client.post("/api/v1/jobs", json=body(protocol_path=path), headers=bearer("alice"))
        assert answer.status_code == 422, path


def test_settings_never_serve_without_tokens_off_the_loopback(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(_env_file=None, api_host="0.0.0.0", auth_mode="local")  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="token"):
        Settings(_env_file=None, env="production")  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="PRINCIPALS"):
        Settings(_env_file=None, auth_mode="token")  # type: ignore[call-arg]


def test_a_name_or_token_cannot_appear_twice() -> None:
    twin = principal("alice", Role.VIEWER)
    with pytest.raises(ValidationError, match="twice"):
        Settings(_env_file=None, auth_mode="token", api_principals=(twin, twin))  # type: ignore[call-arg]


def test_a_new_token_is_long_and_only_its_hash_is_kept(capsys: pytest.CaptureFixture[str]) -> None:
    token = new_token()
    assert token.startswith("mv_")
    assert len(token) >= 43
    made = entry(token, "alice", Role.VIEWER, 30, LATER)
    assert token not in made.model_dump_json()
    assert made.expires_at == LATER + timedelta(days=30)
    with pytest.raises(ValueError, match="90 days"):
        entry(token, "alice", Role.VIEWER, 91, LATER)
    assert main(["--name", "alice", "--role", "viewer", "--days", "7"]) == 0
    shown, record = capsys.readouterr().out.splitlines()
    assert shown.split(": ")[1] not in record


def test_a_good_token_under_another_scheme_is_a_401(client: TestClient) -> None:
    headers = {"Authorization": f"Basic {TOKENS['alice']}"}
    assert client.get("/api/v1/jobs", headers=headers).status_code == 401


def test_a_flood_of_refusals_writes_one_audit_row(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_for(tmp_path, rate_reads_per_minute=1)), base_url=LOOPBACK
    )
    for _ in range(20):
        client.get("/api/v1/me", headers=bearer("alice"))
    app: Any = client.app
    rows = app.state.access.store.audit_rows("alice")
    assert [row.outcome for row in rows].count("limited") == 1


def test_a_flood_of_bad_tokens_writes_a_bounded_audit(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_for(tmp_path, rate_failures_per_minute=3)), base_url=LOOPBACK
    )
    for _ in range(50):
        client.get("/api/v1/jobs", headers={"Authorization": "Bearer wrong"})
    app: Any = client.app
    assert len(app.state.access.store.audit_rows("anonymous")) == 4


def test_a_refusal_is_told_again_in_the_next_window() -> None:
    now = [0.0]
    limiter = RateLimiter(lambda: now[0])
    assert limiter.first_refusal("key")
    assert not limiter.first_refusal("key")
    now[0] = 60.0
    assert limiter.first_refusal("key")


def test_an_erasure_leaves_a_record_without_a_name(client: TestClient) -> None:
    client.post("/api/v1/me/erase", json={"confirm": "alice"}, headers=bearer("alice"))
    rows = client.get("/api/v1/audit", headers=bearer("root")).json()
    assert ("erased", "account_erase") in {(row["actor"], row["action"]) for row in rows}


def test_reading_who_you_are_is_recorded(client: TestClient) -> None:
    client.get("/api/v1/me", headers=bearer("alice"))
    rows = client.get("/api/v1/audit", headers=bearer("root")).json()
    assert ("alice", "account_read") in {(row["actor"], row["action"]) for row in rows}
