"""Real companies on the screens (Stage 24b, decision D-14).

One file per company with what the SEC filings say, what the model says and whether a simulation
can start from it, and an index for search. Everything is rebuilt by a command, and everything says
where it came from: a rank is by public float, a forecast is research, a case rests on assumptions.
"""

from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, Field, StringConstraints

from multiverse_contracts.companies import CompanyDossier, Sector, SupportStatus
from multiverse_contracts.forecasting import LiveCompany
from multiverse_contracts.normalized import Text
from multiverse_contracts.primitives import ContractModel

RANK_LABEL = "Ranked by public float from the 10-K cover, not by market capitalization"
FORECAST_LABEL = "Research forecast, not approved for the product and not advice"


class RankEvidence(ContractModel):
    rank: int = Field(ge=1)
    public_float_usd: float = Field(gt=0)
    float_as_of: date
    float_correction: float = Field(
        default=1,
        ge=1,
        description="What the filed value was divided by: a scale error of the filer.",
    )


class RealCompany(ContractModel):
    """One file of ``data/companies``."""

    dossier: CompanyDossier
    evidence: RankEvidence
    financial: bool = Field(description="Bank, insurer or REIT: margins and capex do not apply.")
    forecast: LiveCompany | None = None
    forecast_note: Text | None = Field(default=None, description="Why there is no forecast.")
    case_id: Annotated[str, StringConstraints(pattern=r"^case-[0-9a-z-]{1,60}$")] | None = None
    case_note: Text | None = Field(
        default=None, description="Why a run cannot start here, or what stands in for missing tags."
    )


class RealCompanyRow(ContractModel):
    """One line of the index: enough to search and to show a result."""

    company_id: str
    cik: str
    name: str
    ticker: str | None = None
    sector: Sector
    country: str
    evidence: RankEvidence
    support_status: SupportStatus
    revenue_quarters: int = Field(ge=0)
    has_forecast: bool
    has_case: bool


class RealIndex(ContractModel):
    universe_id: str
    as_of: AwareDatetime
    forecast_id: str | None = None
    rank_label: str = RANK_LABEL
    forecast_label: str = FORECAST_LABEL
    companies: tuple[RealCompanyRow, ...]
