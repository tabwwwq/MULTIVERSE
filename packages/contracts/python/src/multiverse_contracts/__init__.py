"""Shared domain contracts of MULTIVERSE (single source of truth, ADR-0008)."""

from multiverse_contracts.manifest import ReproducibilityManifest
from multiverse_contracts.metrics import MetricValue, Period, PeriodType
from multiverse_contracts.primitives import (
    CausalStatus,
    ContractModel,
    CurrencyCode,
    DataOrigin,
    DecimalString,
    MeasureUnit,
    Quantity,
    ResultMode,
    UncertaintyType,
    ValueKind,
)
from multiverse_contracts.version import CONTRACTS_VERSION

__version__ = "0.1.0"

__all__ = [
    "CONTRACTS_VERSION",
    "CausalStatus",
    "ContractModel",
    "CurrencyCode",
    "DataOrigin",
    "DecimalString",
    "MeasureUnit",
    "MetricValue",
    "Period",
    "PeriodType",
    "Quantity",
    "ReproducibilityManifest",
    "ResultMode",
    "UncertaintyType",
    "ValueKind",
]
