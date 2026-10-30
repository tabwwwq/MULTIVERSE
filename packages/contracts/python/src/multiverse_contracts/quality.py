"""Gate B: the financial dataset audit, its checks and the dataset manifest (Stage 14).

Every check states what it measured and a status. ``blocked`` is an honest answer: the
data cannot support the next step yet, and the check says why. Dataset size is counted
in usable examples, never in downloaded files (prompt 14).
"""

from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.normalized import Cik10, Text
from multiverse_contracts.pit import KnowledgeView, Sha256
from multiverse_contracts.primitives import ContractModel

CheckId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]


class CheckStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    BLOCKED = "blocked"
    """The data cannot support the next step yet; the check says what is missing."""


class Measure(ContractModel):
    name: Text
    value: str = Field(min_length=1, max_length=200)


class GateCheck(ContractModel):
    check_id: CheckId
    title: Text
    status: CheckStatus
    summary: Text
    measures: tuple[Measure, ...] = ()
    findings: tuple[Text, ...] = Field(default=(), description="Specific cases, at most 40.")
    companies: tuple[Cik10, ...] = Field(default=(), description="Companies a finding concerns.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.status is not CheckStatus.PASS and not (self.findings or self.measures):
            raise ValueError("a check that does not pass shows what it found")
        if len(self.findings) > 40:
            raise ValueError("at most 40 findings; the rest go into the measures")
        return self


class ExampleCount(ContractModel):
    """Trainable examples: company and forecast origin with enough history and a target."""

    history_quarters: int = Field(ge=1, le=40)
    horizon_quarters: int = Field(ge=1, le=40)
    examples: int = Field(ge=0)
    companies: int = Field(ge=0)
    origins: int = Field(ge=0)


class CompanyDecision(ContractModel):
    cik: Cik10
    name: Text
    include: bool
    reasons: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.include and not self.reasons:
            raise ValueError("an excluded company states why")
        return self


class GateVerdict(StrEnum):
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    BLOCKED = "blocked"


class GateManifest(ContractModel):
    """The audited dataset: what it holds, how much is usable, and its hash."""

    dataset_id: str = Field(pattern=r"^gate-b-[0-9]{8}-[0-9a-f]{12}$")
    sha256: Sha256 = Field(description="Of the canonical examples table.")
    data_cutoff: AwareDatetime
    view: KnowledgeView
    target_metric: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    first_origin: date
    last_origin: date
    companies: tuple[CompanyDecision, ...] = Field(min_length=1)
    example_counts: tuple[ExampleCount, ...] = Field(min_length=1)
    pit_snapshot_id: str = Field(pattern=r"^pit-[0-9]{8}-[0-9a-f]{12}$")
    synthetic_macro: bool
    checks: tuple[GateCheck, ...] = Field(min_length=1)
    verdict: GateVerdict
    verdict_reasons: tuple[Text, ...] = ()
    contracts_version: str
    created_at: AwareDatetime = Field(description="Not part of the hash.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.dataset_id.endswith(self.sha256[:12]):
            raise ValueError("the dataset is named by its hash")
        if self.first_origin > self.last_origin:
            raise ValueError("origins run forward")
        statuses = {check.status for check in self.checks}
        blocking = CheckStatus.FAIL in statuses or CheckStatus.BLOCKED in statuses
        if blocking != (self.verdict is GateVerdict.BLOCKED):
            raise ValueError("the gate is blocked exactly when a check fails or is blocked")
        if self.verdict is not GateVerdict.PASSED and not self.verdict_reasons:
            raise ValueError("a gate that does not simply pass says why")
        if self.verdict is GateVerdict.PASSED and CheckStatus.WARNING in statuses:
            raise ValueError("warnings make the verdict passed_with_warnings")
        if self.view is KnowledgeView.LATEST:
            raise ValueError("the audited dataset is point-in-time, never latest")
        return self
