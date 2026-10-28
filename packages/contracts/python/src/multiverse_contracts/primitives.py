"""Primitive value types shared by every MULTIVERSE module.

Exact numbers (money, shares, fractions) travel as decimal strings, never as JSON
floats: floats cannot represent accounting values exactly (docs/09). The finance
package converts them with ``decimal.Decimal``.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

DecimalString = Annotated[
    str,
    StringConstraints(pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"),
    Field(description="Exact decimal number as a string, for example '4213587912' or '-0.25'."),
]

CurrencyCode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z]{3}$"),
    Field(description="ISO 4217 currency code, for example 'USD'."),
]


class ContractModel(BaseModel):
    """Base of every contract: strict types, no unknown fields, immutable instances."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        # Serialized output always contains fields that have defaults, so consumers
        # (the TypeScript types) can rely on them being present.
        json_schema_serialization_defaults_required=True,
    )


class ValueKind(StrEnum):
    """Where a number comes from in time (PRD FR-RE-01)."""

    OBSERVED = "observed"
    FORECAST = "forecast"
    SIMULATED = "simulated"


class DataOrigin(StrEnum):
    """Whether a number describes real reported data or synthetic demo data (PRD SYN-04)."""

    EMPIRICAL = "empirical"
    SYNTHETIC = "synthetic"


class ResultMode(StrEnum):
    """Inference mode shown in the trust header of every result (PRD §6)."""

    DEMO = "demo"
    EMPIRICAL_FORECAST = "empirical_forecast"
    CAUSAL_STUDY = "causal_study"
    FICTIONAL_EXPLORATORY = "fictional_exploratory"


class UncertaintyType(StrEnum):
    """What an interval around a number means (PRD §6, docs/08)."""

    NONE = "none"
    PREDICTIVE_QUANTILES = "predictive_quantiles"
    CONDITIONAL_MODEL_QUANTILES = "conditional_model_quantiles"
    CALIBRATED_INTERVAL = "calibrated_interval"


class CausalStatus(StrEnum):
    """Identification status of a result. Never raised automatically (PRD FR-CA-02)."""

    NOT_ASSESSED = "not_assessed"
    ASSUMPTION_BASED = "assumption_based"
    DIAGNOSTICS_PASSED = "diagnostics_passed"


class MeasureUnit(StrEnum):
    """Unit of a quantity. Percentages are fractions; changes of shares are percentage points."""

    CURRENCY = "currency"
    FRACTION = "fraction"
    PERCENTAGE_POINTS = "percentage_points"
    RATIO = "ratio"
    COUNT = "count"
    SHARES = "shares"
    QUARTERS = "quarters"


class Quantity(ContractModel):
    """A number together with its unit. Currency is required exactly when the unit is money."""

    value: DecimalString
    unit: MeasureUnit
    currency: CurrencyCode | None = None

    @model_validator(mode="after")
    def _currency_matches_unit(self) -> Self:
        if self.unit is MeasureUnit.CURRENCY and self.currency is None:
            raise ValueError("currency is required when unit is 'currency'")
        if self.unit is not MeasureUnit.CURRENCY and self.currency is not None:
            raise ValueError("currency is only allowed when unit is 'currency'")
        return self
