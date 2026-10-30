"""Macroeconomic series, their vintages and the as-of join with financial quarters (Stage 13).

A macro value is usable from the moment it was published, not from the period it
describes: December's CPI is labelled December but published in January, and the first
GDP estimate of a quarter is revised twice within three months and again for years.
Every observation therefore carries when it became available and how that is known
(ADR-0020). A join cell holds a macro feature for one company quarter at one cutoff,
made only of observations available at the cutoff, with their provenance.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.normalized import Cik10, Text
from multiverse_contracts.pit import CalendarQuarter, Sha256
from multiverse_contracts.primitives import ContractModel, DecimalString

SeriesId = Annotated[str, StringConstraints(pattern=r"^[a-z]+:[A-Za-z0-9_.]+$")]
FeatureName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]


class Frequency(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class SeasonalAdjustment(StrEnum):
    NOT_ADJUSTED = "not_adjusted"
    ADJUSTED = "adjusted"
    ADJUSTED_ANNUAL_RATE = "adjusted_annual_rate"
    NOT_APPLICABLE = "not_applicable"


class VintageSupport(StrEnum):
    """What the source keeps of earlier publications."""

    FULL = "full"
    """Every published value with its real-time period (ALFRED)."""
    ARCHIVE = "archive"
    """Dated snapshots of the whole database (WDI archives, or our own dated downloads)."""
    NONE = "none"
    """Only current values; acceptable only for values that are not revised."""


class AvailabilityBasis(StrEnum):
    """How the moment a value became available is known."""

    VINTAGE = "vintage"
    """The source's real-time start of this value: evidence."""
    SNAPSHOT = "snapshot"
    """A dated snapshot contained it: evidence that it was available by then (late side)."""
    SCHEDULE = "schedule"
    """An unrevised value with a fixed publication rule (an ECB reference rate at 16:00 CET)."""
    ESTIMATED = "estimated"
    """No evidence of the first release: never usable as a feature."""


EVIDENCED = frozenset(
    {AvailabilityBasis.VINTAGE, AvailabilityBasis.SNAPSHOT, AvailabilityBasis.SCHEDULE}
)


class Transform(StrEnum):
    """How observations inside a company quarter become one feature value."""

    QUARTER_MEAN = "quarter_mean"
    """Mean of the monthly values whose month falls in the quarter (all of them needed)."""
    QUARTER_MAX = "quarter_max"
    """Largest monthly value in the quarter (a recession month makes the quarter 1)."""
    END_OF_PERIOD = "end_of_period"
    """The last daily value on or before the quarter end, at most 10 days earlier."""
    YOY_LAST_MONTH = "yoy_last_month"
    """Last month of the quarter against the same month a year earlier, one vintage."""
    YOY_QUARTER = "yoy_quarter"
    """Quarterly value against the same quarter a year earlier, one vintage."""
    LATEST_YEAR = "latest_year"
    """The latest annual value available at the cutoff, never a year after the quarter."""


class MacroSeries(ContractModel):
    """One registered series: what it measures and how it is published and revised."""

    series_id: SeriesId = Field(description="Source prefix and the source's own code.")
    source_id: str = Field(min_length=2, max_length=40)
    dataset_id: str = Field(min_length=2, max_length=60)
    title: Text
    geography: str = Field(min_length=2, max_length=10, description="ISO code or area (US, EA).")
    frequency: Frequency
    unit: Text
    seasonal_adjustment: SeasonalAdjustment
    period_label: Text = Field(description="Which date of the period the source uses as label.")
    release_timezone: str = Field(min_length=2, max_length=40)
    publication_lag: Text = Field(description="Typical delay from period end to first release.")
    revision_cadence: Text
    business_days: Text = Field(description="Weekends, holidays and how gaps are treated.")
    vintage_support: VintageSupport
    feature: FeatureName
    transform: Transform
    attribution: Text
    notes: Text | None = None


class MacroObservation(ContractModel):
    """One value of one period as published during one interval of time."""

    series_id: SeriesId
    period_start: date
    period_end: date
    value: DecimalString | None = Field(description="Empty when the source marks it missing.")
    available_from: AwareDatetime
    available_to: AwareDatetime | None = Field(
        default=None, description="When a later publication replaced it; empty while current."
    )
    basis: AvailabilityBasis
    source_vintage: date | None = Field(default=None, description="The source's vintage date.")
    raw_sha256: Sha256 | None = None
    synthetic: bool = False

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.period_start > self.period_end:
            raise ValueError("a period starts before it ends")
        if self.available_to is not None and self.available_to <= self.available_from:
            raise ValueError("an interval of availability ends after it starts")
        return self


class MacroCellState(StrEnum):
    OBSERVED = "observed"
    """Every input published by the cutoff."""
    NOT_YET_RELEASED = "not_yet_released"
    """An input of the quarter was not published by the cutoff."""
    UNAVAILABLE = "unavailable"
    """The source is not in the store: no key, no owner decision, or no download yet."""
    NOT_COVERED = "not_covered"
    """The series does not reach back to the quarter."""
    UNUSABLE = "unusable"
    """Inputs exist, but when they were first published is not evidenced."""


class MacroInput(ContractModel):
    period_start: date
    period_end: date
    value: DecimalString
    available_from: AwareDatetime
    basis: AvailabilityBasis
    raw_sha256: Sha256 | None = None


class MacroCell(ContractModel):
    """One macro feature for one company quarter, as available at the cutoff."""

    cik: Cik10
    calendar_quarter: CalendarQuarter
    lag: int = Field(ge=0)
    window_start: date
    window_end: date
    feature: FeatureName
    series_id: SeriesId
    transform: Transform
    state: MacroCellState
    mask: bool
    value: DecimalString | None = None
    inputs: tuple[MacroInput, ...] = ()
    synthetic: bool = False
    reason: Text | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.mask != (self.state is MacroCellState.OBSERVED):
            raise ValueError("the mask is true exactly for observed cells")
        if self.mask != (self.value is not None):
            raise ValueError("a cell has a value exactly when its mask is true")
        if self.mask and not self.inputs:
            raise ValueError("a value names the observations it was made from")
        if self.mask and any(i.basis not in EVIDENCED for i in self.inputs):
            raise ValueError("a value is made only of inputs whose release is evidenced")
        if not self.mask and self.reason is None:
            raise ValueError("an empty cell states why it is empty")
        if self.window_start > self.window_end:
            raise ValueError("a window starts before it ends")
        return self
