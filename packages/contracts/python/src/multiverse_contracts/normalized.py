"""Canonical financial values normalized from SEC XBRL facts (Stage 11, ADR-0018).

One row is one metric of one company for one fiscal period under one revision policy.
It names the source facts and their signs, how they were combined, the filing that made
the value knowable, and what is doubtful about it. Missing stays missing, with a reason.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.metrics import ConceptName, LineageMethod
from multiverse_contracts.primitives import ContractModel, CurrencyCode, DecimalString

Accession = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")]
Cik10 = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}$")]
Text = Annotated[str, StringConstraints(min_length=1, max_length=400)]


class FiscalPeriod(StrEnum):
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    FY = "FY"


class PeriodKind(StrEnum):
    """Flows cover a period; balance sheet items and share counts are instant values."""

    DURATION = "duration"
    INSTANT = "instant"


class Revision(StrEnum):
    """Which filing's number is used when a later filing reports the same period again."""

    ORIGINAL = "original"
    LATEST = "latest"


class ConceptRelation(StrEnum):
    """How a candidate concept relates to the metric (the concept hierarchy)."""

    PRIMARY = "primary"
    EQUIVALENT = "equivalent"
    NARROWER = "narrower"
    BROADER = "broader"


class QualityFlag(StrEnum):
    RESTATED = "restated"
    FROM_AMENDMENT = "from_amendment"
    NEGATIVE_EXPENSE = "negative_expense"
    NEGATIVE_DERIVED = "negative_derived"
    CONCEPT_FALLBACK = "concept_fallback"
    BROADER_CONCEPT = "broader_concept"
    NARROWER_CONCEPT = "narrower_concept"
    INCLUDES_NONCONTROLLING = "includes_noncontrolling"
    CONCEPT_DISAGREEMENT = "concept_disagreement"
    CONFLICT_IN_FILING = "conflict_in_filing"
    NON_USD = "non_usd"
    FIFTY_THREE_WEEKS = "fifty_three_weeks"
    MIXED_ROUNDING = "mixed_rounding"
    SCALE_MISMATCH = "scale_mismatch"


DERIVED_METHODS = frozenset(
    {
        LineageMethod.YTD_TO_QUARTER,
        LineageMethod.FY_MINUS_NINE_MONTHS,
        LineageMethod.FY_MINUS_THREE_QUARTERS,
    }
)


class SourceFact(ContractModel):
    """One XBRL fact as filed, and the sign with which it enters the value."""

    concept: ConceptName
    unit: str = Field(min_length=1, max_length=40)
    period_start: date | None = None
    period_end: date
    value: DecimalString
    accession: Accession
    form: str = Field(min_length=2, max_length=12)
    filed: date
    sign: Literal[1, -1] = 1


class ConceptCheck(ContractModel):
    """Reconciliation evidence: another candidate concept reported for the same period."""

    concept: ConceptName
    relation: ConceptRelation
    value: DecimalString
    difference: DecimalString = Field(description="Chosen value minus this value.")


class NormalizedValue(ContractModel):
    cik: Cik10
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    fiscal_year: int = Field(ge=1990, le=2200)
    fiscal_period: FiscalPeriod
    period_kind: PeriodKind
    period_start: date | None = Field(default=None, description="Empty for instant values.")
    period_end: date
    revision: Revision
    value: DecimalString | None
    missing_reason: Text | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    currency: CurrencyCode | None = None
    concept: ConceptName | None = Field(
        default=None, description="The concept chosen for the metric; empty for calculated values."
    )
    method: LineageMethod | None = None
    formula: Text | None = None
    accession: Accession | None = Field(
        default=None, description="The filing that made the value knowable: its latest source."
    )
    filed: date | None = Field(default=None, description="Knowledge date: latest source filed.")
    sources: tuple[SourceFact, ...] = ()
    alternatives: tuple[ConceptCheck, ...] = ()
    original_value: DecimalString | None = Field(
        default=None, description="On a restated latest value: the value as first filed."
    )
    quality: QualitySeverity
    flags: tuple[QualityFlag, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.value is None) == (self.missing_reason is None):
            raise ValueError("a value or a missing reason, exactly one; missing is never zero")
        if (self.period_kind is PeriodKind.INSTANT) != (self.period_start is None):
            raise ValueError("only instant values have no period start")
        if self.period_start is not None and self.period_start >= self.period_end:
            raise ValueError("a period starts before it ends")
        if self.quality is QualitySeverity.BLOCKING and self.value is not None:
            raise ValueError("a blocking quality problem withholds the value")
        if (QualityFlag.RESTATED in self.flags) != (self.original_value is not None):
            raise ValueError("a restated value keeps its original value, and only it does")
        if self.original_value is not None and self.revision is not Revision.LATEST:
            raise ValueError("only the latest revision can be a restatement")
        if self.value is None:
            if self.sources or self.method is not None:
                raise ValueError("a missing value has no sources and no method")
            return self
        if self.method is None or self.accession is None or self.filed is None:
            raise ValueError("a value states its method, accession and filing date")
        if self.method is LineageMethod.REPORTED and len(self.sources) != 1:
            raise ValueError("a reported value has exactly one source fact")
        if self.method in DERIVED_METHODS and len(self.sources) < 2:
            raise ValueError("a derived value has at least two source facts")
        if self.method is LineageMethod.CALCULATED and self.formula is None:
            raise ValueError("a calculated value states its formula")
        if self.method is not LineageMethod.CALCULATED and self.concept is None:
            raise ValueError("a value taken from filings names its concept")
        total = sum((Decimal(s.value) * s.sign for s in self.sources), Decimal(0))
        if total != Decimal(self.value):
            raise ValueError("the value must equal the signed sum of its source facts")
        latest = max(s.filed for s in self.sources)
        if self.filed != latest:
            raise ValueError("the knowledge date is the latest filing date of the sources")
        if self.accession not in {s.accession for s in self.sources if s.filed == latest}:
            raise ValueError("the accession is that of a latest source")
        if self.period_kind is PeriodKind.INSTANT and self.method is not LineageMethod.REPORTED:
            raise ValueError("instant values are reported, never derived")
        return self
