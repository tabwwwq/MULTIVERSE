"""Config validation: bad settings fail at startup, secrets stay hidden."""

import os
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from multiverse_config import Environment, Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("MULTIVERSE_"):
            monkeypatch.delenv(name)


def test_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.env is Environment.LOCAL
    assert settings.allow_network_downloads is False
    assert settings.cloud_spend_limit_usd == Decimal("0")
    assert settings.fred_api_key is None


def test_env_example_is_a_valid_configuration() -> None:
    settings = Settings(_env_file=REPO_ROOT / ".env.example")

    assert settings.env is Environment.LOCAL


def test_typo_in_env_file_fails(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MULTIVERSE_ALLOW_NETWORK_DOWNLOAD=true\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="allow_network_download"):
        Settings(_env_file=env_file)


def test_environment_variables_are_read_with_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_ENV", "ci")
    monkeypatch.setenv("MULTIVERSE_API_PORT", "9000")

    settings = Settings(_env_file=None)

    assert settings.env is Environment.CI
    assert settings.api_port == 9000


def test_unknown_profile_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_ENV", "staging")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_downloads_require_sec_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_ALLOW_NETWORK_DOWNLOADS", "true")

    with pytest.raises(ValidationError, match="SEC_USER_AGENT"):
        Settings(_env_file=None)


def test_sec_user_agent_needs_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_SEC_USER_AGENT", "MULTIVERSE research")

    with pytest.raises(ValidationError, match="contact email"):
        Settings(_env_file=None)


def test_production_forbids_debug_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_ENV", "production")
    monkeypatch.setenv("MULTIVERSE_LOG_LEVEL", "DEBUG")

    with pytest.raises(ValidationError, match="production"):
        Settings(_env_file=None)


def test_negative_spend_limit_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_CLOUD_SPEND_LIMIT_USD", "-1")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secret_never_appears_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_value = "fake-fred-value-for-tests"
    monkeypatch.setenv("MULTIVERSE_FRED_API_KEY", fake_value)

    settings = Settings(_env_file=None)

    assert fake_value not in repr(settings)
    assert fake_value not in settings.model_dump_json()
    assert settings.fred_api_key is not None
    assert settings.fred_api_key.get_secret_value() == fake_value
