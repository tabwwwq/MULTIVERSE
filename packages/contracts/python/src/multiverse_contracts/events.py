"""Corporate decisions as verified events (Stage 19): the labels causal work may stand on.

An event keeps apart what was announced and what was executed: a headline is a statement of
intention, never a treatment. Every field is either read from a primary document, with the
place it was read, or listed as unknown. Reviews are named, and an AI reviewer says so.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.forecasting import Name, Score
from multiverse_contracts.normalized import Text
from multiverse_contracts.pit import Sha256
from multiverse_contracts.primitives import ContractModel

Cik = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}$")]
Accession = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")]
EventId = Annotated[str, StringConstraints(pattern=r"^evt-[0-9]{10}-[a-z_]+-[0-9]{8}$")]


class EventType(StrEnum):
    RND_CHANGE = "rnd_change"
    ACQUISITION = "acquisition"
    LAYOFF = "layoff"
    DIVESTITURE = "divestiture"
    CAPEX_CHANGE = "capex_change"
    REFINANCING = "refinancing"


class CompletionStatus(StrEnum):
    ANNOUNCED = "announced"
    PARTIAL = "partial"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


class EventUnit(StrEnum):
    """One meaning each: +40% of a budget is not +40 points of revenue (docs/05)."""

    USD = "usd"
    HEADCOUNT = "headcount"
    PERCENT_OF_WORKFORCE = "percent_of_workforce"
    PERCENT_CHANGE = "percent_change"
    POINTS_OF_REVENUE = "points_of_revenue"
    UNKNOWN = "unknown"


class EventMagnitude(ContractModel):
    value: Score | None = None
    unit: EventUnit = EventUnit.UNKNOWN
    measures: Text = Field(description="What the number is, in the document's own terms.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.value is None) != (self.unit is EventUnit.UNKNOWN):
            raise ValueError("a magnitude has both a value and a unit, or neither")
        return self


class EventFunding(ContractModel):
    """Shares of the consideration; all None when the documents do not say."""

    cash: Score | None = Field(default=None, ge=0, le=1)
    debt: Score | None = Field(default=None, ge=0, le=1)
    equity: Score | None = Field(default=None, ge=0, le=1)
    other: Score | None = Field(default=None, ge=0, le=1)
    note: Text | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        shares = [s for s in (self.cash, self.debt, self.equity, self.other) if s is not None]
        if shares and abs(sum(shares) - 1) > 0.01:
            raise ValueError("known funding shares add up to one")
        return self


class EventEvidence(ContractModel):
    """Where a fact was read. The summary is in the reviewer's words, not a quotation."""

    role: Literal["announcement", "execution", "magnitude", "funding", "status", "context"]
    url: Annotated[str, StringConstraints(pattern=r"^https://www\.sec\.gov/Archives/edgar/data/")]
    accession: Accession
    form: str = Field(min_length=1, max_length=20)
    filed_at: AwareDatetime = Field(description="EDGAR acceptance: when it became public.")
    item: str | None = Field(default=None, max_length=20, description="8-K item, when one applies.")
    locator: Text = Field(description="Page, section or paragraph of the document.")
    summary: Text
    document_sha256: Sha256


class EventReview(ContractModel):
    reviewer: Name
    kind: Literal["human", "ai"]
    decision: Literal["confirmed", "corrected", "rejected", "unsure"]
    confidence: Literal["high", "medium", "low"]
    notes: Text | None = None
    reviewed_at: AwareDatetime


class CorporateEvent(ContractModel):
    event_id: EventId
    cik: Cik
    company: str = Field(min_length=1, max_length=200)
    division: Annotated[str, StringConstraints(pattern=r"^[A-K]$")]
    deregistered: bool = Field(description="Whether the company has since left EDGAR reporting.")
    event_type: EventType
    intention: Text | None = Field(default=None, description="What was announced, if anything.")
    executed: Text | None = Field(default=None, description="What was done, as far as documented.")
    announced_at: AwareDatetime | None = Field(
        default=None, description="The first public document: the start of any event window."
    )
    effective_on: date | None = Field(default=None, description="Closing or effective date.")
    reporting_lag_days: int | None = Field(
        default=None, description="From the effective date to the document that reports it."
    )
    magnitude: EventMagnitude
    funding: EventFunding = EventFunding()
    completion: CompletionStatus
    unknown_fields: tuple[Name, ...] = Field(default=(), description="Said aloud, never hidden.")
    confounded_by: tuple[Text, ...] = Field(
        default=(), description="Other events or shocks in the same window, as documented."
    )
    stratum: Name = Field(description="The sampling stratum it was drawn from.")
    evidence: tuple[EventEvidence, ...] = Field(min_length=1)
    reviews: tuple[EventReview, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.intention is None and self.executed is None:
            raise ValueError("an event states an intention, an execution or both")
        if self.completion is CompletionStatus.COMPLETED and self.executed is None:
            raise ValueError("a completed event says what was executed")
        if self.announced_at is not None and not any(
            e.filed_at <= self.announced_at for e in self.evidence
        ):
            raise ValueError("the announcement moment comes from a document of the event")
        return self


class EventCandidate(ContractModel):
    """A filing that may hold an event: a pointer to read, never a label."""

    candidate_id: str = Field(min_length=1, max_length=80)
    cik: Cik
    company: str = Field(min_length=1, max_length=200)
    division: Annotated[str, StringConstraints(pattern=r"^[A-K]$")]
    deregistered: bool
    event_type: EventType
    stratum: Name
    accession: Accession
    form: str = Field(min_length=1, max_length=20)
    items: tuple[str, ...] = ()
    filed_at: AwareDatetime
    url: Annotated[str, StringConstraints(pattern=r"^https://www\.sec\.gov/Archives/edgar/data/")]


class CandidateSample(ContractModel):
    """The drawn sample: rules, seed and counts, so it can be repeated."""

    sample_id: Annotated[str, StringConstraints(pattern=r"^evs-[0-9]{8}-[0-9a-f]{12}$")]
    sha256: Sha256
    universe_id: str
    seed: int
    population: dict[Name, int] = Field(description="Filings per stratum before drawing.")
    drawn: dict[Name, int] = Field(description="Filings per stratum after drawing.")
    candidates: tuple[EventCandidate, ...]
    contracts_version: str
    created_at: AwareDatetime = Field(description="Not part of the hash.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.sample_id.rsplit("-", 1)[1] != self.sha256[:12]:
            raise ValueError("the sample is named by its SHA-256")
        return self


class EventRegistry(ContractModel):
    registry_version: str = Field(min_length=1, max_length=20)
    sample_id: str
    guidelines: str = Field(min_length=1, max_length=200)
    events: tuple[CorporateEvent, ...]
    rejected: tuple["RejectedCandidate", ...] = Field(
        default=(), description="Read and not an event: kept, so the sample stays honest."
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [e.event_id for e in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("event ids are unique")
        return self


class RejectedCandidate(ContractModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    reason: Text
    reviewer: Name
    kind: Literal["human", "ai"]


class OverlapCell(ContractModel):
    first: EventType
    second: EventType
    pairs: int = Field(ge=0, description="Events of one firm within the window of each other.")


class CountRow(ContractModel):
    key: str = Field(min_length=1, max_length=60)
    count: int = Field(ge=0)


class QualityAudit(ContractModel):
    """What the registry can carry, measured; the verdict gates causal work (docs/05)."""

    registry_version: str
    sample_id: str
    candidates_read: int = Field(ge=0)
    events: int = Field(ge=0)
    rejected: int = Field(ge=0)
    by_type: tuple[CountRow, ...]
    by_completion: tuple[CountRow, ...]
    by_division: tuple[CountRow, ...]
    deregistered_events: int = Field(ge=0)
    human_reviewed: int = Field(ge=0)
    double_reviewed: int = Field(ge=0)
    reviewer_agreement: Score | None = Field(
        default=None, description="Share of double-reviewed events with the same decision."
    )
    unknown_rate: tuple[CountRow, ...] = Field(description="Events missing each field.")
    confounded: int = Field(ge=0)
    overlap: tuple[OverlapCell, ...]
    overlap_window_days: int = Field(ge=1)
    index_overlap: tuple[CountRow, ...] = Field(
        default=(), description="Events with an unread filing of that 8-K item in the window."
    )
    credible_for_causal_work: bool
    blockers: tuple[Text, ...]
    contracts_version: str


EventRegistry.model_rebuild()
