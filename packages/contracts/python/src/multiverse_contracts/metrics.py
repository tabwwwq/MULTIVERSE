"""A single displayed number with everything needed to trust it (PRD NFR-PROV-01)."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.primitives import (
    ContractModel,
    DataOrigin,
    Quantity,
    UncertaintyType,
    ValueKind,
)


class PeriodType(StrEnum):
    """Flows cover a period (quarter, year, trailing twelve months); stocks are instant."""

    FISCAL_QUARTER = "fiscal_quarter"
    FISCAL_YEAR = "fiscal_year"
    TTM = "ttm"
    INSTANT = "instant"


class Period(ContractModel):
    """When a value applies. ``end_date`` is the period end, or the date of an instant value."""

    type: PeriodType
    end_date: date
    fiscal_year: int | None = Field(default=None, ge=1900, le=2200)
    fiscal_quarter: int | None = Field(default=None, ge=1, le=4)

    @model_validator(mode="after")
    def _fields_match_type(self) -> Self:
        needs_year = self.type in (PeriodType.FISCAL_QUARTER, PeriodType.FISCAL_YEAR)
        if needs_year and self.fiscal_year is None:
            raise ValueError(f"fiscal_year is required for period type '{self.type}'")
        if (self.type is PeriodType.FISCAL_QUARTER) != (self.fiscal_quarter is not None):
            raise ValueError("fiscal_quarter is required for, and only for, 'fiscal_quarter'")
        if self.type in (PeriodType.INSTANT, PeriodType.TTM) and self.fiscal_year is not None:
            raise ValueError(f"fiscal_year is not used for period type '{self.type}'")
        return self


ConceptName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9-]*:[A-Za-z][A-Za-z0-9]*$"),
    Field(description="Taxonomy concept, e.g. 'us-gaap:Revenues'."),
]


class LineageMethod(StrEnum):
    """How a quarterly number was derived from what the filing reports (docs/04)."""

    REPORTED = "reported"
    YTD_TO_QUARTER = "ytd_to_quarter"
    FY_MINUS_NINE_MONTHS = "fy_minus_nine_months"
    FY_MINUS_THREE_QUARTERS = "fy_minus_three_quarters"
    CALCULATED = "calculated"


class Lineage(ContractModel):
    """Where a number comes from inside its filings. Stage 11 extends this with full lineage."""

    concepts: tuple[ConceptName, ...] = Field(min_length=1)
    method: LineageMethod
    formula: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _calculated_needs_formula(self) -> Self:
        if self.method is LineageMethod.CALCULATED and self.formula is None:
            raise ValueError("a calculated value must state its formula")
        return self


class MetricValue(ContractModel):
    """One number shown to a user or passed between modules.

    ``quantity`` is ``None`` when the value is missing. Missing is never zero:
    a reason is mandatory (docs/04, PRD FR-CO-04).
    """

    metric: str = Field(pattern=r"^[a-z][a-z0-9_]*$", description="Metric slug, e.g. 'revenue'.")
    quantity: Quantity | None
    missing_reason: str | None = Field(default=None, min_length=1)
    kind: ValueKind
    data_origin: DataOrigin
    period: Period
    as_of: AwareDatetime = Field(description="Knowledge cutoff: only facts published by then.")
    source_ids: tuple[str, ...] = ()
    uncertainty_type: UncertaintyType = UncertaintyType.NONE
    lineage: Lineage | None = None

    @model_validator(mode="after")
    def _check_honesty_rules(self) -> Self:
        if self.quantity is None and self.missing_reason is None:
            raise ValueError("a missing value needs missing_reason; never report it as zero")
        if self.quantity is not None and self.missing_reason is not None:
            raise ValueError("missing_reason is only allowed when quantity is null")
        if (
            self.kind is ValueKind.OBSERVED
            and self.data_origin is DataOrigin.EMPIRICAL
            and not self.source_ids
        ):
            raise ValueError("an observed empirical value must cite at least one source")
        if self.kind is ValueKind.OBSERVED and self.uncertainty_type is not UncertaintyType.NONE:
            raise ValueError("observed values carry no forecast uncertainty")
        return self
