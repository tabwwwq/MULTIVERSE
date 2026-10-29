"""Saved scenarios, their revisions and exported reports (PRD FR-LB, FR-RP, docs/09).

A scenario has editable metadata (name, tags, notes) and an append-only list of
revisions. A revision never changes: an edit is a new revision that names its parent.
After a report is exported from a revision, that revision is locked, and every export
is its own snapshot, so a later export never replaces an earlier one (FR-RP-03).

In V1 all of this lives in the browser of one device (decision D-07). The same contract
is what ``POST /api/v1/scenarios`` and ``GET /api/v1/scenarios/{id}/revisions`` will use.
"""

import hashlib
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.decisions import ScenarioDraft
from multiverse_contracts.manifest import ReproducibilityManifest
from multiverse_contracts.primitives import ContractModel, CurrencyCode, ResultMode

_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
Tag = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,31}$"),
    Field(description="Lowercase letters, digits and dashes, for example 'rnd'."),
]

NOTEBOOK_SCHEMA_VERSION = 1


class RevisionRef(ContractModel):
    """A specific revision of a specific scenario."""

    scenario_id: str = Field(pattern=_UUID)
    revision: int = Field(ge=1)


class ScenarioRevision(ContractModel):
    """One immutable state of a scenario."""

    revision: int = Field(ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    derived_from: RevisionRef | None = Field(
        default=None, description="Set when the scenario was duplicated from another one."
    )
    created_at: AwareDatetime
    draft: ScenarioDraft
    mode: ResultMode
    currency: CurrencyCode
    result_status: Literal["not_run", "completed", "failed"]
    result_id: str | None = Field(default=None, pattern=_UUID)
    exported: bool = Field(description="A report was exported: the revision is locked.")

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.parent_revision is not None and self.parent_revision >= self.revision:
            raise ValueError("a revision's parent must come before it")
        if (self.result_status == "not_run") != (self.result_id is None):
            raise ValueError("a result ID is required for, and only for, a run result")
        if self.mode is ResultMode.DEMO and self.draft.data_origin != "synthetic":
            raise ValueError("demo mode goes with synthetic data (PRD SYN-01)")
        return self


class ScenarioRecord(ContractModel):
    scenario_id: str = Field(pattern=_UUID)
    name: str = Field(min_length=1, max_length=120)
    tags: tuple[Tag, ...] = Field(default=(), max_length=10)
    notes: str = Field(default="", max_length=5000)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    revisions: tuple[ScenarioRevision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.name != self.name.strip():
            raise ValueError("the name has no leading or trailing spaces")
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("tags are unique")
        numbers = [revision.revision for revision in self.revisions]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("revisions are numbered 1, 2, 3 ... without gaps")
        if self.revisions[0].parent_revision is not None:
            raise ValueError("the first revision has no parent in the same scenario")
        company = self.revisions[0].draft.company_id
        if any(revision.draft.company_id != company for revision in self.revisions):
            raise ValueError("all revisions of a scenario are for the same company")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot come before created_at")
        return self


class ReportSnapshot(ContractModel):
    """One exported report. Never edited, never replaced (PRD FR-RP-02, FR-RP-03)."""

    report_id: str = Field(pattern=_UUID)
    source: RevisionRef
    created_at: AwareDatetime
    format: Literal["markdown"]
    file_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.md$")
    content: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest: ReproducibilityManifest

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if digest != self.content_sha256:
            raise ValueError("content_sha256 does not match the report content")
        if self.manifest.scenario_id != self.source.scenario_id:
            raise ValueError("the manifest names the exported scenario")
        if self.manifest.revision != self.source.revision:
            raise ValueError("the manifest names the exported revision")
        if self.manifest.data_origin == "synthetic" and not self.file_name.endswith("_DEMO.md"):
            raise ValueError("a demo report file name ends with _DEMO (PRD SYN-05)")
        return self


class NotebookExport(ContractModel):
    """The JSON file a notebook is exported to and imported from (PRD FR-LB-03)."""

    format: Literal["multiverse-notebook"]
    schema_version: int = Field(ge=1)
    contracts_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    exported_at: AwareDatetime
    scenarios: tuple[ScenarioRecord, ...] = ()
    reports: tuple[ReportSnapshot, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.schema_version > NOTEBOOK_SCHEMA_VERSION:
            raise ValueError("the file was written by a newer version of MULTIVERSE")
        ids = [record.scenario_id for record in self.scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError("scenario IDs are unique")
        if len({report.report_id for report in self.reports}) != len(self.reports):
            raise ValueError("report IDs are unique")
        by_id = {record.scenario_id: record for record in self.scenarios}
        for report in self.reports:
            record = by_id.get(report.source.scenario_id)
            if record is None or report.source.revision > len(record.revisions):
                raise ValueError(f"report {report.report_id} names a revision that is not here")
            if not record.revisions[report.source.revision - 1].exported:
                raise ValueError(f"report {report.report_id}: its revision is not marked exported")
        return self
