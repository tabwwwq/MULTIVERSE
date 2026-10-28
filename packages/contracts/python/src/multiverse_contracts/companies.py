"""Company identity, listing history and the company dossier (docs/09, Stage 04).

A company has a stable ID that never changes. Tickers and legal names are
histories with dates, because both change over time (PRD FR-CO-01, FR-CO-02).
"""

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.metrics import MetricValue
from multiverse_contracts.primitives import (
    ContractModel,
    CurrencyCode,
    DataOrigin,
    MeasureUnit,
    ValueKind,
)

_SLUG = r"^[a-z][a-z0-9_]*$"
_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

CountryCode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z]{2}$"),
    Field(description="ISO 3166-1 alpha-2 country code, e.g. 'US'."),
]


class Sector(StrEnum):
    SEMICONDUCTORS = "semiconductors"
    SOFTWARE = "software"
    MEDICAL_DEVICES = "medical_devices"
    UTILITIES = "utilities"
    LOGISTICS = "logistics"
    INSTRUMENTS = "instruments"
    INDUSTRIAL_MACHINERY = "industrial_machinery"


class CompanyStatus(StrEnum):
    """Lifecycle of a listed company. Leavers stay in the data to avoid survivorship bias."""

    ACTIVE = "active"
    ACQUIRED = "acquired"
    DELISTED = "delisted"
    BANKRUPT = "bankrupt"


class AccountingStandard(StrEnum):
    US_GAAP = "us_gaap"
    IFRS = "ifrs"


class SupportStatus(StrEnum):
    """Whether MULTIVERSE can work with a company (PRD FC-01, FC-02)."""

    SUPPORTED = "supported"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNSUPPORTED = "unsupported"


class FilingForm(StrEnum):
    FORM_10K = "10-K"
    FORM_10Q = "10-Q"
    FORM_10K_A = "10-K/A"
    FORM_10Q_A = "10-Q/A"
    FORM_20F = "20-F"


class QualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class DatedName(ContractModel):
    """A legal name and the dates it was used. ``valid_to`` is null while it is current."""

    name: str = Field(min_length=1, max_length=200)
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be before valid_from")
        return self


class TickerListing(ContractModel):
    """A ticker on an exchange for a period. Tickers are aliases, never identifiers."""

    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")
    exchange: str = Field(min_length=2, max_length=20)
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be before valid_from")
        return self


def _check_history(items: Sequence[DatedName | TickerListing], label: str) -> None:
    """Periods are in order, do not overlap, and only the last one may still be open."""
    for previous, current in pairwise(items):
        if previous.valid_to is None:
            raise ValueError(f"only the last {label} may be open-ended")
        if current.valid_from <= previous.valid_to:
            raise ValueError(f"{label} periods must be in order and must not overlap")


class Company(ContractModel):
    """Identity of a company. ``company_id`` stays the same through every rename and relisting."""

    company_id: str = Field(pattern=_UUID, description="Stable ID. Never reused, never changes.")
    cik: str | None = Field(
        default=None, pattern=r"^[0-9]{10}$", description="SEC CIK, zero-padded."
    )
    names: tuple[DatedName, ...] = Field(min_length=1)
    listings: tuple[TickerListing, ...] = ()
    sector: Sector
    country: CountryCode
    reporting_currency: CurrencyCode
    accounting_standard: AccountingStandard
    fiscal_year_end: str = Field(
        pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$", description="MM-DD"
    )
    fiscal_52_53_week: bool = False
    status: CompanyStatus = CompanyStatus.ACTIVE
    status_date: date | None = None
    status_note: str | None = Field(default=None, min_length=1)
    data_origin: DataOrigin

    @model_validator(mode="after")
    def _check_history_and_status(self) -> Self:
        _check_history(self.names, "name")
        _check_history(self.listings, "listing")
        active = self.status is CompanyStatus.ACTIVE
        if active == (self.status_date is not None):
            raise ValueError("status_date is required for, and only for, companies that left")
        if active and self.names[-1].valid_to is not None:
            raise ValueError("an active company needs a current name")
        if not active and any(listing.valid_to is None for listing in self.listings):
            raise ValueError("a company that left the market cannot have an open listing")
        return self


class FilingReference(ContractModel):
    """A filing that values come from. Synthetic filings never get a link (no invented sources)."""

    filing_id: str = Field(pattern=r"^[a-z0-9][a-z0-9:_-]{2,63}$")
    form: FilingForm
    accession_number: str = Field(pattern=r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
    period_end: date
    filed_at: AwareDatetime
    url: str | None = Field(default=None, pattern=r"^https://www\.sec\.gov/")
    data_origin: DataOrigin

    @model_validator(mode="after")
    def _check_filing(self) -> Self:
        if self.data_origin is DataOrigin.SYNTHETIC and self.url is not None:
            raise ValueError("a synthetic filing must not link to a document")
        if self.filed_at.date() < self.period_end:
            raise ValueError("a filing cannot be filed before its period ends")
        return self


class CoverageEntry(ContractModel):
    """How many fiscal quarters have a valid value for one metric."""

    metric: str = Field(pattern=_SLUG)
    quarters_valid: int = Field(ge=0)
    quarters_expected: int = Field(ge=0)

    @model_validator(mode="after")
    def _valid_not_above_expected(self) -> Self:
        if self.quarters_valid > self.quarters_expected:
            raise ValueError("quarters_valid cannot exceed quarters_expected")
        return self


class DataQualityFlag(ContractModel):
    code: str = Field(pattern=_SLUG)
    severity: QualitySeverity
    message: str = Field(min_length=1)
    metric: str | None = Field(default=None, pattern=_SLUG)


class CompanyDossier(ContractModel):
    """Everything known about one company at a knowledge cutoff ``as_of``."""

    company: Company
    support_status: SupportStatus
    support_reason: str | None = Field(default=None, min_length=1)
    as_of: AwareDatetime = Field(description="Snapshot cutoff: nothing filed later is included.")
    filings: tuple[FilingReference, ...] = ()
    values: tuple[MetricValue, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    quality_flags: tuple[DataQualityFlag, ...] = ()

    @model_validator(mode="after")
    def _check_dossier(self) -> Self:
        supported = self.support_status is SupportStatus.SUPPORTED
        if supported == (self.support_reason is not None):
            raise ValueError("support_reason is required for, and only for, limited support")
        if self.support_status is SupportStatus.UNSUPPORTED and (self.values or self.coverage):
            raise ValueError("an unsupported company has no values and no coverage")

        filing_ids = [filing.filing_id for filing in self.filings]
        if len(filing_ids) != len(set(filing_ids)):
            raise ValueError("filing ids must be unique")
        origin = self.company.data_origin
        for filing in self.filings:
            if filing.data_origin is not origin:
                raise ValueError("filings must have the same data origin as the company")
            if filing.filed_at > self.as_of:
                raise ValueError(f"filing {filing.filing_id} was filed after the dossier cutoff")

        known = set(filing_ids)
        for value in self.values:
            if value.data_origin is not origin:
                raise ValueError("values must have the same data origin as the company")
            if value.kind is not ValueKind.OBSERVED:
                raise ValueError("a dossier holds observed values only")
            if value.as_of != self.as_of:
                raise ValueError("every value must share the dossier cutoff")
            if not set(value.source_ids) <= known:
                raise ValueError(f"value {value.metric} cites a filing that is not in the dossier")
            quantity = value.quantity
            if (
                quantity is not None
                and quantity.unit is MeasureUnit.CURRENCY
                and quantity.currency != self.company.reporting_currency
            ):
                raise ValueError("amounts must be in the company's reporting currency")
        return self
