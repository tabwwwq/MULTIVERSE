"""The study universe: which companies the datasets are built from, and why (decision D-10).

A universe is drawn once from the archived bulk files of SEC EDGAR, by written rules and
a seed, so anyone with the same two ZIP files draws the same companies. It records the
files it was drawn from, the rules, how many companies each rule left, and per SIC
division how many were eligible and how many were chosen.
"""

from datetime import date
from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.normalized import Cik10, Text
from multiverse_contracts.pit import Sha256
from multiverse_contracts.primitives import ContractModel

Division = Annotated[str, StringConstraints(pattern=r"^[A-K]$")]
SicCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")]


class BulkFile(ContractModel):
    """One archived bulk ZIP file the universe was drawn from."""

    url: str = Field(min_length=1, max_length=400)
    path: str = Field(min_length=1, max_length=400, description="Relative to the raw root.")
    sha256: Sha256
    last_modified: str | None = Field(default=None, description="As the server sent it.")
    downloaded_at: AwareDatetime


class RuleCount(ContractModel):
    """A rule of eligibility and the companies still eligible after it."""

    rule: Text
    remaining: int = Field(ge=0)


class UniverseStratum(ContractModel):
    division: Division
    title: Text
    eligible: int = Field(ge=0)
    quota: int = Field(ge=0, description="Share of the sample, proportional to eligible.")
    selected: int = Field(ge=0)


class UniverseCompany(ContractModel):
    cik: Cik10
    name: Text
    sic: SicCode
    division: Division
    xbrl_10k: int = Field(ge=1, description="XBRL 10-K filings on file.")
    xbrl_10q: int = Field(ge=0, description="XBRL 10-Q filings on file.")
    first_xbrl_filed: date
    last_filed: date
    deregistered: bool = Field(description="A Form 15 is on file: no longer reporting.")
    candidate: bool = Field(description="One of the ten catalog candidates, always included.")


class UniverseManifest(ContractModel):
    universe_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")]
    decision: Text
    seed: int
    size: int = Field(ge=1)
    created_at: AwareDatetime
    sources: tuple[BulkFile, ...] = Field(min_length=2)
    scanned: int = Field(ge=0, description="Companies with a Company Facts file.")
    rules: tuple[RuleCount, ...] = Field(min_length=1)
    strata: tuple[UniverseStratum, ...] = Field(min_length=1)
    companies: tuple[UniverseCompany, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        ciks = [company.cik for company in self.companies]
        if ciks != sorted(set(ciks)):
            raise ValueError("companies are listed once each, by CIK")
        if len(ciks) != self.size:
            raise ValueError(f"{len(ciks)} companies for a universe of {self.size}")
        if self.rules[-1].remaining < self.size:
            raise ValueError("more companies chosen than eligible")
        for stratum in self.strata:
            chosen = sum(company.division == stratum.division for company in self.companies)
            if chosen != stratum.selected:
                raise ValueError(
                    f"division {stratum.division}: {chosen} listed, {stratum.selected} counted"
                )
            if stratum.selected > stratum.eligible:
                raise ValueError(f"division {stratum.division}: more chosen than eligible")
        if sum(s.eligible for s in self.strata) != self.rules[-1].remaining:
            raise ValueError("the strata hold every eligible company")
        return self
