"""Validated runtime settings (ADR-0010).

Invalid configuration fails at startup with a clear message instead of failing
later inside a job. Secrets use ``SecretStr`` so they never appear in logs or reprs.
"""

from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    CI = "ci"
    PRODUCTION = "production"


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
        return self


def load_settings() -> Settings:
    """Read settings from the environment and ``.env``. Call only from composition roots."""
    return Settings()
