"""Point-in-time values, the as-of quarterly panel and its snapshots (Stage 12, ADR-0019).

A value is knowable from the moment its last source filing became public on EDGAR, not
from the end of the period it describes. Every normalized value therefore carries the
interval of knowledge time during which it was the current answer: ``known_from`` (when
a filing made it so) to ``known_to`` (when a later filing replaced it; empty while it is
still current). An as-of query at a cutoff sees exactly the values whose interval
contains the cutoff, so a filing first filed after the cutoff can never reach it.

A panel cell is one company, calendar quarter and metric at one cutoff. Its mask is true
only when a value was knowable at the cutoff; every other state says why it is empty.
"""

from datetime import date, timedelta
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.metrics import ConceptName, LineageMethod
from multiverse_contracts.normalized import (
    Accession,
    Cik10,
    FiscalPeriod,
    NormalizedValue,
    QualityFlag,
    Text,
)
from multiverse_contracts.primitives import ContractModel, CurrencyCode, DecimalString

PIT_POLICY_VERSION = "pit-policy-1"
PANEL_SCHEMA_VERSION = "panel-1"

CalendarQuarter = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}Q[1-4]$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
MetricName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
# A fiscal quarter belongs to the nearest calendar quarter end, so it ends within half a
# quarter of it (a 14-week quarter included).
HALF_QUARTER = timedelta(days=50)


class KnowledgeView(StrEnum):
    """Which value of a period a query returns when filings reported it more than once."""

    ORIGINAL = "original"
    """As first filed, among the filings public at the cutoff."""
    VINTAGE = "vintage"
    """As last filed before the cutoff: what an analyst could know then. Default."""
    LATEST = "latest"
    """As last filed today. Hindsight: never a feature, never in a snapshot."""


POINT_IN_TIME_VIEWS = frozenset({KnowledgeView.ORIGINAL, KnowledgeView.VINTAGE})


class TimePrecision(StrEnum):
    """How the moment a filing became public was determined."""

    ACCEPTED = "accepted"
    """EDGAR's acceptance time, on or after the start of the filing date."""
    FILING_DAY_START = "filing_day_start"
    """Accepted after hours with the next business day as filing date: from that day."""
    FILING_DAY_END = "filing_day_end"
    """Only the filing date is known: from the end of that day (US Eastern)."""


class ValueChange(StrEnum):
    """Why a new interval of knowledge began for one period."""

    FIRST_KNOWN = "first_known"
    VALUE_FILLED = "value_filled"
    VALUE_REVISED = "value_revised"
    VALUE_WITHDRAWN = "value_withdrawn"
    CONFIRMED = "confirmed"
    """Same value, now also reported by a newer filing."""
    REQUALIFIED = "requalified"
    """Same value and sources; other flags, quality or missing reason."""


class SourceTiming(ContractModel):
    accession: Accession
    known_at: AwareDatetime
    precision: TimePrecision


class PitValue(ContractModel):
    """One normalized value during one interval of knowledge time."""

    value: NormalizedValue
    known_from: AwareDatetime
    known_to: AwareDatetime | None = Field(
        default=None, description="When a later filing replaced it; empty while current."
    )
    change: ValueChange
    timings: tuple[SourceTiming, ...] = Field(
        default=(), description="When each source filing became public."
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.known_to is not None and self.known_to <= self.known_from:
            raise ValueError("an interval of knowledge ends after it starts")
        accessions = {source.accession for source in self.value.sources}
        if {timing.accession for timing in self.timings} != accessions:
            raise ValueError("every source filing, and only those, has its timing")
        if any(timing.known_at > self.known_from for timing in self.timings):
            raise ValueError("a value is never known before its sources were public")
        return self


class CellState(StrEnum):
    OBSERVED = "observed"
    """Reported for the quarter by a filing public at the cutoff."""
    DERIVED = "derived"
    """Computed from reported values that were all public at the cutoff."""
    NOT_YET_FILED = "not_yet_filed"
    """The quarter has ended, but its report was not public at the cutoff."""
    NOT_REPORTED = "not_reported"
    """The report was public, the metric is not available in it."""
    BLOCKED = "blocked"
    """Withheld: conflicting values in one filing, or a broken chronology."""
    INACTIVE = "inactive"
    """A Form 15 before the quarter ended, no report after it, the next report overdue."""
    NOT_COVERED = "not_covered"
    """Before the company's first XBRL report, or no fiscal calendar known yet."""


MASKED_STATES = frozenset({CellState.OBSERVED, CellState.DERIVED})


class PanelCell(ContractModel):
    """One company, calendar quarter and metric of the as-of panel."""

    cik: Cik10
    calendar_quarter: CalendarQuarter
    quarter_end: date
    lag: int = Field(ge=0, description="0 is the last calendar quarter ended at the cutoff.")
    metric: MetricName
    state: CellState
    mask: bool = Field(description="True only when a value was knowable at the cutoff.")
    value: DecimalString | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    currency: CurrencyCode | None = None
    fiscal_year: int | None = Field(default=None, ge=1990, le=2200)
    fiscal_period: FiscalPeriod | None = None
    period_start: date | None = None
    period_end: date | None = None
    method: LineageMethod | None = None
    concept: ConceptName | None = None
    accession: Accession | None = None
    known_from: AwareDatetime | None = None
    flags: tuple[QualityFlag, ...] = ()
    reason: Text | None = Field(default=None, description="Why the cell is empty.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.mask != (self.state in MASKED_STATES):
            raise ValueError("the mask is true exactly for observed and derived cells")
        if self.mask != (self.value is not None):
            raise ValueError("a cell has a value exactly when its mask is true")
        if self.mask and (self.known_from is None or self.method is None):
            raise ValueError("a value states when it became known and how it was made")
        if self.mask and self.period_end is None:
            raise ValueError("a value states the period it measures")
        if not self.mask and self.reason is None:
            raise ValueError("an empty cell states why it is empty")
        if self.period_end is not None and abs(self.period_end - self.quarter_end) > HALF_QUARTER:
            raise ValueError("a cell's period ends near its calendar quarter end")
        return self


class AlertKind(StrEnum):
    PERIOD_AFTER_FILING = "period_after_filing"
    """A metric fact ends after the filing that reported it: an estimate, never a value."""
    FILING_DATE_MISMATCH = "filing_date_mismatch"
    """Company Facts and the filing index give different filing dates."""
    ACCEPTED_AFTER_FILING_DATE = "accepted_after_filing_date"
    """EDGAR accepted the filing more than one day after its filing date."""
    MISSING_ACCEPTANCE = "missing_acceptance"
    """The filing is not in the archived filing index: its filing date is used."""
    AMENDMENT_BEFORE_ORIGINAL = "amendment_before_original"
    REPORT_OUT_OF_ORDER = "report_out_of_order"
    """A report became public before the report of an earlier period."""
    LATE_REPORT = "late_report"
    """Filed after the longest regular deadline (10-Q 45 days, 10-K 90 days)."""
    QUARTERS_DO_NOT_SUM = "quarters_do_not_sum"
    """Four reported quarters differ from the fiscal year beyond rounding."""
    DEREGISTRATION = "deregistration"
    """A Form 15 was filed and no periodic report followed it."""


class ChronologyAlert(ContractModel):
    kind: AlertKind
    severity: QualitySeverity
    cik: Cik10
    accession: Accession | None = None
    metric: MetricName | None = None
    concept: ConceptName | None = None
    period_end: date | None = None
    known_at: AwareDatetime | None = None
    detail: Text


class StateCount(ContractModel):
    state: CellState
    cells: int = Field(ge=0)


class SnapshotInput(ContractModel):
    """One raw archive file the warehouse was built from."""

    path: str = Field(min_length=1, max_length=300)
    sha256: Sha256
    url: str = Field(min_length=1, max_length=300)
    downloaded_at: AwareDatetime


class PitSnapshotManifest(ContractModel):
    """An immutable as-of panel: the same cutoff always gives the same cells and hash."""

    snapshot_id: str = Field(pattern=r"^pit-[0-9]{8}-[0-9a-f]{12}$")
    sha256: Sha256 = Field(description="Of the canonical cells file; names the snapshot.")
    cutoff: AwareDatetime
    cutoff_label: str = Field(min_length=10, max_length=40, description="As requested.")
    view: KnowledgeView
    quarters: int = Field(ge=1, le=80)
    ciks: tuple[Cik10, ...] = Field(min_length=1)
    metrics: tuple[MetricName, ...] = Field(min_length=1)
    cells: int = Field(ge=1)
    state_counts: tuple[StateCount, ...]
    policy_version: str = PIT_POLICY_VERSION
    panel_schema_version: str = PANEL_SCHEMA_VERSION
    contracts_version: str
    inputs: tuple[SnapshotInput, ...]
    alerts: int = Field(ge=0, description="Chronology alerts of these companies.")
    created_at: AwareDatetime = Field(description="Not part of the hash.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.view not in POINT_IN_TIME_VIEWS:
            raise ValueError("a snapshot is point-in-time: original or vintage, never latest")
        if not self.snapshot_id.endswith(self.sha256[:12]):
            raise ValueError("the snapshot is named by its hash")
        states = [count.state for count in self.state_counts]
        if len(states) != len(set(states)):
            raise ValueError("each state is counted once")
        if sum(count.cells for count in self.state_counts) != self.cells:
            raise ValueError("the state counts add up to the cells")
        if self.cells != len(self.ciks) * self.quarters * len(self.metrics):
            raise ValueError("the panel is complete: every company, quarter and metric")
        if self.created_at < self.cutoff:
            raise ValueError("a snapshot is made after its cutoff")
        return self


class EntityAttributeName(StrEnum):
    NAME = "name"
    TICKER = "ticker"
    EXCHANGE = "exchange"
    SIC = "sic"


class EntityAttribute(ContractModel):
    """A company name, ticker, exchange or industry code over the dates it applied.

    With no ``effective_from`` only the current value is known: it applies from the
    moment it was observed, never backwards, so today's ticker or sector cannot leak
    into an older cutoff.
    """

    cik: Cik10
    attribute: EntityAttributeName
    value: str = Field(min_length=1, max_length=200)
    effective_from: date | None = None
    effective_to: date | None = Field(default=None, description="Exclusive.")
    observed_at: AwareDatetime
    source: Text

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("an attribute stops applying after it starts")
        return self
