"""Validated runtime settings (ADR-0010).

Invalid configuration fails at startup with a clear message instead of failing
later inside a job. Secrets use ``SecretStr`` so they never appear in logs or reprs.
"""

from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    CI = "ci"
    PRODUCTION = "production"


class Role(StrEnum):
    """Who may do what (Stage 24). Each role holds the rights of the one before it."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class ApiPrincipal(BaseModel):
    """One account of the API. Only the hash of its token is kept, and every token expires."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=40)
    role: Role
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: AwareDatetime


class Settings(BaseSettings):
    """All runtime settings. Environment variables use the ``MULTIVERSE_`` prefix."""

    model_config = SettingsConfigDict(
        env_prefix="MULTIVERSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    env: Environment = Environment.LOCAL
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    data_dir: Path = Path("var/data")
    # Raw source files (Stage 10): immutable, never committed, within a disk budget.
    raw_dir: Path = Path("var/raw")
    raw_budget_mb: int = Field(default=200, ge=1)
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    # The web app on this machine may read the API; nothing else may (Stage 18).
    web_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    # Names this API answers to: any other Host header is a rebinding attempt (Stage 24).
    api_allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")
    # "local" trusts this machine and only its loopback; anything else needs tokens (ADR-0032).
    auth_mode: Literal["local", "token"] = "local"
    api_principals: tuple[ApiPrincipal, ...] = ()
    rate_reads_per_minute: int = Field(default=300, ge=1)
    rate_writes_per_minute: int = Field(default=30, ge=1)
    rate_failures_per_minute: int = Field(default=10, ge=1)
    max_body_bytes: int = Field(default=262_144, ge=1024)
    max_active_jobs: int = Field(default=8, ge=1)
    daily_compute_seconds: int = Field(default=43_200, ge=1)
    audit_retention_days: int = Field(default=90, ge=1)
    # Downloads from SEC, FRED and others stay off until the owner enables them (Stage 09-10).
    allow_network_downloads: bool = False
    sec_user_agent: str | None = None
    fred_api_key: SecretStr | None = None
    # Paid compute is forbidden by default: 0 means no cloud spending at all (PRD NFR-COST-01).
    cloud_spend_limit_usd: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.sec_user_agent is not None and "@" not in self.sec_user_agent:
            raise ValueError(
                "MULTIVERSE_SEC_USER_AGENT must include a contact email (SEC fair access policy)"
            )
        if self.allow_network_downloads and self.sec_user_agent is None:
            raise ValueError(
                "MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true requires MULTIVERSE_SEC_USER_AGENT"
            )
        if self.env is Environment.PRODUCTION and self.log_level == "DEBUG":
            raise ValueError("DEBUG logging is not allowed in the production profile")
        if self.auth_mode == "local" and self.env is Environment.PRODUCTION:
            raise ValueError("the production profile needs MULTIVERSE_AUTH_MODE=token")
        if self.auth_mode == "local" and self.api_host not in LOOPBACK:
            raise ValueError("MULTIVERSE_AUTH_MODE=local serves the loopback address only")
        if self.auth_mode == "token" and not self.api_principals:
            raise ValueError("MULTIVERSE_AUTH_MODE=token needs MULTIVERSE_API_PRINCIPALS")
        names = [principal.name for principal in self.api_principals]
        hashes = [principal.token_sha256 for principal in self.api_principals]
        if len(set(names)) != len(names) or len(set(hashes)) != len(hashes):
            raise ValueError("MULTIVERSE_API_PRINCIPALS holds a name or a token twice")
        return self


def load_settings() -> Settings:
    """Read settings from the environment and ``.env``. Call only from composition roots."""
    return Settings()
