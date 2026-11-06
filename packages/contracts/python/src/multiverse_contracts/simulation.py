"""Paired Monte Carlo (Stage 22): the case a run starts from, and what it reports.

A case holds one company at one cutoff: its opening balance, its central path and the history
its shocks are resampled from, each input with how it is known. A report holds what the paths
showed. Its probabilities are conditional on the assumed model: nothing here has been calibrated
against outcomes, and the contract does not accept a report that says otherwise.
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.decisions import Decision
from multiverse_contracts.forecasting import Name, Score
from multiverse_contracts.normalized import Text
from multiverse_contracts.pit import Sha256
from multiverse_contracts.primitives import ContractModel, CurrencyCode, DataOrigin, DecimalString
from multiverse_contracts.results import ScenarioResult

CaseId = Annotated[str, StringConstraints(pattern=r"^case-[0-9a-z-]{1,60}$")]
ReportId = Annotated[str, StringConstraints(pattern=r"^sim-[0-9]{8}-[0-9a-f]{12}$")]
Share = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
CONDITIONAL_LABEL = "Conditional on the assumed model, not validated"


class CaseTranche(ContractModel):
    name: Name
    principal: DecimalString
    annual_rate: DecimalString
    maturity_quarter: int | None = Field(default=None, ge=1)
    floating: bool = False


class CaseOpening(ContractModel):
    cash: DecimalString
    trade_nwc: DecimalString
    ppe: DecimalString
    intangibles: DecimalString
    goodwill: DecimalString
    non_operating_assets: DecimalString
    tranches: tuple[CaseTranche, ...]
    trailing_ebitda: tuple[DecimalString, ...] = Field(max_length=3)
    trailing_interest: tuple[DecimalString, ...] = Field(max_length=3)


class CasePolicy(ContractModel):
    tax_rate: DecimalString
    depreciation_rate: DecimalString
    amortization_rate: DecimalString
    cash_yield: DecimalString
    minimum_cash: DecimalString
    revolver_limit: DecimalString
    revolver_rate: DecimalString
    marginal_debt_rate: DecimalString
    dividend_payout: DecimalString
    max_leverage: DecimalString
    min_interest_cover: DecimalString


class CaseDrivers(ContractModel):
    last_year_revenue: tuple[DecimalString, ...] = Field(
        min_length=4, max_length=4, description="The last four known quarters, oldest first."
    )
    rd_ratio: Score = Field(ge=0, le=1)
    cogs_share: Score = Field(ge=0, le=1, description="Of cash costs other than R&D.")
    capex_ratio: Score = Field(ge=0)
    nwc_ratio: Score = Field(ge=-1, le=1)


class CentralPath(ContractModel):
    """Where the company goes with no shock. Shocks are deviations from it."""

    growth: tuple[Score, ...] = Field(
        min_length=4, description="Symmetric growth over the same quarter a year earlier."
    )
    margin: tuple[Score, ...] = Field(min_length=4, description="EBITDA margin of the quarter.")
    growth_source: Text
    margin_source: Text

    @model_validator(mode="after")
    def _same_length(self) -> Self:
        if len(self.growth) != len(self.margin):
            raise ValueError("growth and margin cover the same quarters")
        return self


class ShockRow(ContractModel):
    quarter_end: date
    values: tuple[Score, ...]


class ShockHistory(ContractModel):
    """One row per calendar quarter: a draw takes a whole row, so links between columns survive."""

    variables: tuple[Name, ...] = Field(min_length=1)
    rows: tuple[ShockRow, ...] = Field(min_length=8)
    persistence_growth: Score = Field(ge=0, lt=1)
    persistence_margin: Score = Field(ge=0, lt=1)
    mean_block_quarters: Score = Field(ge=1)
    base_short_rate: Score = Field(ge=0, description="Fed funds at the cutoff, as a fraction.")
    peers: int = Field(ge=1, description="Firms of the division behind the sector columns.")
    method: Text

    @model_validator(mode="after")
    def _rows_fit(self) -> Self:
        days = [row.quarter_end for row in self.rows]
        if days != sorted(set(days)):
            raise ValueError("rows are unique and in order")
        if any(len(row.values) != len(self.variables) for row in self.rows):
            raise ValueError("each row has one value per variable")
        return self


class CapitalInputs(ContractModel):
    risk_free: DecimalString
    equity_risk_premium: DecimalString
    beta: DecimalString
    pre_tax_cost_of_debt: DecimalString
    tax_rate: DecimalString
    debt_weight: DecimalString
    terminal_growth: DecimalString


class CaseInput(ContractModel):
    """How one input is known: never leave an assumption looking like a fact."""

    name: Name
    origin: Literal["observed", "implied", "assumed", "model"]
    note: Text


class CaseHistoryPoint(ContractModel):
    period_end: date
    fiscal_label: str = Field(min_length=1)
    filed_at: date
    source_id: str = Field(min_length=1)
    revenue: DecimalString | None = None
    ebitda: DecimalString | None = None
    fcf: DecimalString | None = None
    net_debt: DecimalString | None = None


class SimulationCase(ContractModel):
    contracts_version: str
    case_id: CaseId
    company_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    company_name: str = Field(min_length=1)
    as_of: date
    balance_date: date = Field(
        description="Of the opening balance: the last quarter end reported by the cutoff."
    )
    currency: CurrencyCode
    data_origin: DataOrigin
    dataset_id: str | None = None
    dataset_sha256: Sha256 | None = None
    model_id: str | None = None
    opening: CaseOpening
    policy: CasePolicy
    drivers: CaseDrivers
    central: CentralPath
    shocks: ShockHistory
    capital: CapitalInputs
    inputs: tuple[CaseInput, ...] = Field(min_length=1)
    history: tuple[CaseHistoryPoint, ...] = ()

    @property
    def horizon(self) -> int:
        return len(self.central.growth)


class SimulationSettings(ContractModel):
    paths: int = Field(ge=1, le=100_000)
    seed: int = Field(ge=0, le=2**31 - 1)
    batch_paths: int = Field(default=250, ge=1, le=10_000)
    max_redraws: int = Field(default=3, ge=0, le=10)
    lock_macro: bool = Field(
        default=False,
        description="Macro columns stay at zero, and sector columns lose what macro explains.",
    )
    shock_scale: Score = Field(default=1.0, gt=0, le=4)
    mean_block_quarters: Score | None = Field(
        default=None, ge=1, description="None takes the block length of the case."
    )


class SimulationRequest(ContractModel):
    """A run for the queue. Every run goes through a worker, however small it is."""

    kind: Literal["simulation"] = "simulation"
    idempotency_key: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{8,80}$")]
    owner: Name
    case_id: CaseId
    decision: Decision
    settings: SimulationSettings
    max_runtime_seconds: int = Field(ge=1, description="Over all attempts together.")
    spend_limit_usd: Score = Field(default=0, ge=0)
    rate_usd_per_hour: Score = Field(default=0, ge=0, description="Zero on the owner's machine.")
    overnight: bool = False


class RiskRow(ContractModel):
    """The share of paths where something happens at least once within the horizon."""

    risk: Literal[
        "funding_shortfall",
        "covenant_breach",
        "below_minimum_cash",
        "negative_fcff_year",
    ]
    label: str = Field(min_length=1)
    scenario: Literal["baseline", "alt_a"]
    probability: Share
    standard_error: Share = Field(description="Monte Carlo error only, not model error.")
    upper_95: Share = Field(
        description="Wilson bound: no event on n paths still leaves room for a small probability."
    )


class ValueRow(ContractModel):
    """Enterprise or equity value across the paths where it is defined."""

    metric: Literal["enterprise_value", "equity_value", "ev_change"]
    scenario: Literal["baseline", "alt_a"]
    p1: DecimalString | None = None
    p10: DecimalString | None = None
    p50: DecimalString | None = None
    p90: DecimalString | None = None
    p99: DecimalString | None = None
    mean: DecimalString | None = None
    undefined_share: Share


class ConvergenceRow(ContractModel):
    """A statistic on the first ``paths`` paths, against its value on all of them."""

    paths: int = Field(ge=1)
    statistic: Name
    label: str = Field(min_length=1)
    value: Score
    standard_error: Score = Field(ge=0)
    gap_to_final: Score = Field(ge=0, description="Absolute difference from the longest run.")
    within_two_errors: bool


class TailDriver(ContractModel):
    name: Name
    label: str = Field(min_length=1)
    value: Score
    unit: Literal["points_of_growth", "points_of_margin", "points_of_rate", "yes_no"]


class TailRow(ContractModel):
    """One of the worst paths for the alternate, with what drove it."""

    rank: int = Field(ge=1)
    path: int = Field(ge=0)
    ev_change: DecimalString
    drivers: tuple[TailDriver, ...]


class SensitivityRow(ContractModel):
    """The same run with one choice of the shock model changed."""

    variant: Name
    label: str = Field(min_length=1)
    paths: int = Field(ge=1)
    ebitda_p10: DecimalString
    ebitda_p50: DecimalString
    ebitda_p90: DecimalString
    ev_change_p50: DecimalString
    covenant_probability: Share


class SimulationDiagnostics(ContractModel):
    paths: int = Field(ge=1)
    redraws: int = Field(ge=0)
    invalid_by_code: tuple[tuple[Name, int], ...] = ()
    clipped_share: Share = Field(description="Quarters where a shock met a hard bound.")
    ev_undefined_share: Share
    path_identities_checked: int = Field(ge=1)
    history_quarters: int = Field(ge=1)
    simulated_correlation: Score | None = Field(
        default=None, description="Of the sector growth and sector margin shocks drawn."
    )
    historical_correlation: Score | None = None
    effective_sample_size: Score = Field(gt=0)
    seconds: Score = Field(ge=0, description="Not part of the identity of a report.")
    flags: tuple[Text, ...] = ()


class SimulationManifest(ContractModel):
    """Everything needed to replay a report. Two equal manifests give equal numbers."""

    report_id: ReportId
    contracts_version: str
    finance_version: str
    simulation_version: str
    code_version: str = Field(min_length=1)
    case_id: CaseId
    case_sha256: Sha256
    decision_sha256: Sha256
    dataset_id: str | None = None
    dataset_sha256: Sha256 | None = None
    model_id: str | None = None
    settings: SimulationSettings
    shock_model: Text
    created_at: AwareDatetime = Field(description="Not part of the hash.")


class SimulationReport(ContractModel):
    """One finished run."""

    manifest: SimulationManifest
    validation: Literal["conditional_non_validated"]
    probability_label: Literal["Conditional on the assumed model, not validated"]
    result: ScenarioResult
    risks: tuple[RiskRow, ...] = Field(min_length=1)
    values: tuple[ValueRow, ...] = Field(min_length=1)
    convergence: tuple[ConvergenceRow, ...] = Field(min_length=1)
    tails: tuple[TailRow, ...] = ()
    sensitivity: tuple[SensitivityRow, ...] = ()
    inputs: tuple[CaseInput, ...] = Field(min_length=1)
    diagnostics: SimulationDiagnostics

    @model_validator(mode="after")
    def _honest(self) -> Self:
        if self.result.calibrated:
            raise ValueError("no calibration exists for these paths: they stay conditional")
        if self.result.paths != self.diagnostics.paths:
            raise ValueError("the report and its result describe the same paths")
        return self
