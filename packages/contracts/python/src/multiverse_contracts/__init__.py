"""Shared domain contracts of MULTIVERSE (single source of truth, ADR-0008)."""

from multiverse_contracts.companies import (
    AccountingStandard,
    Company,
    CompanyDossier,
    CompanyStatus,
    CountryCode,
    CoverageEntry,
    DataQualityFlag,
    DatedName,
    FilingForm,
    FilingReference,
    QualitySeverity,
    Sector,
    SupportStatus,
    TickerListing,
)
from multiverse_contracts.manifest import ReproducibilityManifest
from multiverse_contracts.metrics import (
    ConceptName,
    Lineage,
    LineageMethod,
    MetricValue,
    Period,
    PeriodType,
)
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
    "AccountingStandard",
    "CausalStatus",
    "Company",
    "CompanyDossier",
    "CompanyStatus",
    "ConceptName",
    "ContractModel",
    "CountryCode",
    "CoverageEntry",
    "CurrencyCode",
    "DataOrigin",
    "DataQualityFlag",
    "DatedName",
    "DecimalString",
    "FilingForm",
    "FilingReference",
    "Lineage",
    "LineageMethod",
    "MeasureUnit",
    "MetricValue",
    "Period",
    "PeriodType",
    "QualitySeverity",
    "Quantity",
    "ReproducibilityManifest",
    "ResultMode",
    "Sector",
    "SupportStatus",
    "TickerListing",
    "UncertaintyType",
    "ValueKind",
]
