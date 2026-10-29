"""Rows of the raw metadata index and the audit manifest of one run (ADR-0017).

The index has one row per stored object: identical bytes are never stored twice. The
manifest records every request of a run, including the ones that stored nothing.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# The manifest names the setting that held the User-Agent, never its value (it has an email).
UserAgentRef = Literal["MULTIVERSE_SEC_USER_AGENT"]
USER_AGENT_REF: UserAgentRef = "MULTIVERSE_SEC_USER_AGENT"


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RawObject(Record):
    """One immutable file in the raw archive, as the source published it."""

    source_id: str
    dataset_id: str
    key: str = Field(description="CIK10 for company files, a quarter or a file name for bulk.")
    cik: str | None = None
    url: str
    path: str = Field(description="Relative to the raw root, with forward slashes.")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    file_format: Literal["json", "zip"]
    content_encoding: str = Field(description="HTTP compression on the wire, e.g. gzip.")
    http_status: int
    content_length: int | None = Field(default=None, description="As sent, before decoding.")
    last_modified: str | None = None
    etag: str | None = None
    downloaded_at: AwareDatetime
    run_id: str
    filing_count: int | None = Field(default=None, description="Filings the file lists.")
    latest_filing_id: str | None = Field(default=None, description="Accession number.")
    latest_filed: date | None = None
    user_agent_ref: UserAgentRef = USER_AGENT_REF
    licence: str
    terms_checked_on: date
    catalog_version: str


class Outcome(StrEnum):
    NEW = "new"
    UNCHANGED = "unchanged"
    NOT_MODIFIED = "not_modified"
    FRESH_IN_ARCHIVE = "fresh_in_archive"
    STALE_RESPONSE = "stale_response"
    PROBED = "probed"
    FAILED = "failed"


class FetchRecord(Record):
    dataset_id: str
    key: str
    url: str
    outcome: Outcome
    requests: int = Field(ge=0, description="HTTP requests made, retries included.")
    checked_at: AwareDatetime
    sha256: str | None = None
    size_bytes: int | None = None
    content_length: int | None = None
    last_modified: str | None = None
    error: str | None = None


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class RunManifest(Record):
    """Audit record of one command: what was asked, what the source answered, what was kept."""

    run_id: str
    mode: Literal["sample", "probe", "bulk"]
    started_at: datetime
    finished_at: datetime
    status: RunStatus
    message: str | None = None
    user_agent_ref: UserAgentRef = USER_AGENT_REF
    rate_per_second: str
    catalog_version: str
    decision_status: str
    decision_scope: str | None
    decided_on: date | None
    records: tuple[FetchRecord, ...] = ()

    @property
    def requests(self) -> int:
        return sum(record.requests for record in self.records)

    @property
    def bytes_new(self) -> int:
        return sum(r.size_bytes or 0 for r in self.records if r.outcome is Outcome.NEW)
