"""Valuation and risk studio (Stage 23): what a value rests on, shown row by row.

Enterprise value and equity value are separate outputs, joined by an explicit bridge. A report
carries a fixed label: these are model values, never a verified market value. Price per share is
outside V1 to V3 (D-06); a share count only tells how much of equity today's holders keep.
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.forecasting import Name, Score
from multiverse_contracts.normalized import Text
from multiverse_contracts.pit import Sha256
from multiverse_contracts.primitives import ContractModel, CurrencyCode, DecimalString
from multiverse_contracts.simulation import CapitalInputs, CaseId, CaseInput, ReportId, Share

ValuationId = Annotated[str, StringConstraints(pattern=r"^val-[0-9]{8}-[0-9a-f]{12}$")]
VALUE_LABEL = "Model value, not a verified market value"
SENSITIVITY_LABEL = "Predictive sensitivity, not causal"


class StudioScenario(ContractModel):
    scenario: Literal["bear", "base", "bull"]
    label: str = Field(min_length=1)
    weight: DecimalString
    growth_shift: Score = Field(description="Added to central growth in every quarter.")
    margin_shift: Score = Field(description="Added to the central EBITDA margin.")


class StudioInputs(ContractModel):
    """What the studio assumes beyond the case. Each of these is a choice, and editable."""

    exit_multiple: DecimalString = Field(description="EV / EBITDA, assumed: no market data here.")
    other_senior_claims: DecimalString
    diluted_shares: DecimalString | None = None
    diluted_shares_source: Text | None = None
    wacc_steps: tuple[DecimalString, ...] = Field(min_length=3, description="Around WACC.")
    growth_steps: tuple[DecimalString, ...] = Field(min_length=3, description="Around g.")
    margin_points: DecimalString
    growth_points: DecimalString
    capex_points: DecimalString
    scenarios: tuple[StudioScenario, ...] = Field(min_length=3, max_length=3)
    scenario_paths: int = Field(ge=100, le=10_000)
    seed: int = Field(ge=0)
    maturity_wall_quarter: int = Field(ge=1)


class DcfRow(ContractModel):
    """One quarter: from statements to present value. Every column is shown, so it can be redone."""

    quarter: int = Field(ge=1)
    period_end: date
    label: str = Field(min_length=1)
    revenue: DecimalString
    ebitda: DecimalString
    adjusted_ebitda: DecimalString
    ebit: DecimalString
    tax_on_ebit: DecimalString
    d_and_a: DecimalString
    capex: DecimalString
    delta_nwc: DecimalString
    transactions: DecimalString
    fcff: DecimalString
    fcff_recurring: DecimalString
    discount_factor: Score = Field(gt=0, le=1)
    present_value: DecimalString


class DebtRow(ContractModel):
    period_end: date
    label: str = Field(min_length=1)
    cash: DecimalString
    term_debt: DecimalString
    revolver: DecimalString
    shortfall: DecimalString
    net_debt: DecimalString
    interest_expense: DecimalString
    leverage: Score | None = None
    interest_cover: Score | None = None


class TerminalRow(ContractModel):
    method: Literal["gordon", "exit_multiple"]
    label: str = Field(min_length=1)
    terminal_value: DecimalString | None = None
    present_terminal: DecimalString | None = None
    enterprise_value: DecimalString | None = None
    terminal_share: Score | None = Field(
        default=None, description="Of EV; above 1 when explicit years are negative in sum."
    )
    implied_growth: Score | None = None
    implied_multiple: Score | None = None
    reason: Text | None = None


class BridgeView(ContractModel):
    enterprise_value: DecimalString | None = None
    debt: DecimalString
    cash: DecimalString
    other_senior_claims: DecimalString
    non_operating_assets: DecimalString
    equity_value: DecimalString | None = None


class SensitivityCell(ContractModel):
    wacc: Score
    growth: Score
    enterprise_value: DecimalString | None = Field(
        default=None, description="None where WACC is at or below growth: no value exists."
    )
    equity_value: DecimalString | None = None


class ValuationView(ContractModel):
    scenario: Literal["baseline", "alt_a"]
    label: str = Field(min_length=1)
    rows: tuple[DcfRow, ...] = Field(min_length=4)
    debt: tuple[DebtRow, ...] = Field(min_length=1)
    present_explicit: DecimalString
    terminals: tuple[TerminalRow, ...] = Field(min_length=2)
    bridge: BridgeView
    sensitivity: tuple[SensitivityCell, ...] = Field(min_length=1)


class TornadoRow(ContractModel):
    driver: Name
    label: str = Field(min_length=1)
    low_label: str = Field(min_length=1)
    high_label: str = Field(min_length=1)
    low_value: DecimalString
    high_value: DecimalString


class ScenarioRow(ContractModel):
    scenario: Literal["bear", "base", "bull"]
    label: str = Field(min_length=1)
    weight: DecimalString
    paths: int = Field(ge=1)
    ev_p10: DecimalString
    ev_p50: DecimalString
    ev_p90: DecimalString
    ev_mean: DecimalString
    equity_p50: DecimalString
    covenant_probability: Share
    shortfall_probability: Share


class StressRow(ContractModel):
    key: Name
    label: str = Field(min_length=1)
    enterprise_value: DecimalString | None = None
    ev_change: DecimalString | None = None
    lowest_cash: DecimalString
    peak_leverage: Score | None = None
    lowest_interest_cover: Score | None = None
    first_breach: str | None = Field(default=None, description="The quarter, if any.")
    peak_shortfall: DecimalString


class QualityCheck(ContractModel):
    key: Name
    label: str = Field(min_length=1)
    passed: bool
    detail: Text


class ValuationManifest(ContractModel):
    valuation_id: ValuationId
    contracts_version: str
    finance_version: str
    simulation_version: str
    code_version: str = Field(min_length=1)
    case_id: CaseId
    case_sha256: Sha256
    decision_sha256: Sha256
    inputs_sha256: Sha256
    simulation_report_id: ReportId
    created_at: AwareDatetime = Field(description="Not part of the hash.")


class ValuationReport(ContractModel):
    contracts_version: str
    manifest: ValuationManifest
    value_label: Literal["Model value, not a verified market value"]
    sensitivity_label: Literal["Predictive sensitivity, not causal"]
    company_name: str = Field(min_length=1)
    as_of: date
    balance_date: date
    currency: CurrencyCode
    capital: CapitalInputs
    wacc: Score = Field(gt=0)
    cost_of_equity: Score = Field(gt=0)
    inputs: "StudioInputs"
    case_inputs: tuple[CaseInput, ...] = Field(min_length=1)
    views: tuple[ValuationView, ...] = Field(min_length=2, max_length=2)
    tornado: tuple[TornadoRow, ...] = Field(min_length=1)
    base_value: DecimalString = Field(description="EV of the view the tornado moves.")
    scenarios: tuple[ScenarioRow, ...] = Field(min_length=3, max_length=3)
    weighted_enterprise_value: DecimalString
    stress: tuple[StressRow, ...] = Field(min_length=1)
    adverse_title: str = Field(min_length=1)
    adverse_story: tuple[Text, ...] = Field(min_length=1)
    checks: tuple[QualityCheck, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _honest(self) -> Self:
        if not all(check.passed for check in self.checks if check.key.startswith("must_")):
            raise ValueError("a report with a failed required check is not a report")
        return self
