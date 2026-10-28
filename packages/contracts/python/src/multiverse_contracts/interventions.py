"""Catalog of decision types: units, ranges, defaults and mechanisms (docs/16, PRD FR-DE).

The catalog is the single definition of every parameter a decision can have. The
contract validators read their ranges from it, the web form is generated from it, and
it is what ``GET /api/v1/interventions/types`` will return.

Defaults are starting values for the form, not estimates. Each one names its source:
an accounting rule, a statutory rate, a design choice, or a placeholder that a later
stage replaces with a measured value. Planning ranges are design defaults too until
Stage 14 measures historical ranges on real data.

``python -m multiverse_contracts.catalog`` writes it to ``catalog/interventions.json``.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from multiverse_contracts.distributions import Distribution, TriangularRange, distribution_points
from multiverse_contracts.primitives import ContractModel, DecimalString
from multiverse_contracts.version import CONTRACTS_VERSION


class InterventionType(StrEnum):
    """The six decision types of V1 (PRD FR-DE-01, docs/16 "recommended first six")."""

    RND_CHANGE = "rnd_change"
    WORKFORCE_RESTRUCTURE = "workforce_restructure"
    ACQUISITION = "acquisition"
    DIVESTITURE = "divestiture"
    CAPEX_EXPANSION = "capex_expansion"
    DEBT_REFINANCE = "debt_refinance"


class ValueUnit(StrEnum):
    """Unit of a parameter value. Fractions are shares: 0.25 means 25 %."""

    FRACTION = "fraction"
    PERCENTAGE_POINTS = "percentage_points"
    USD = "usd"
    QUARTERS = "quarters"
    YEARS = "years"
    MONTHS_OF_SALARY = "months_of_salary"


class MagnitudeUnit(StrEnum):
    """What the size of a decision is measured against (PRD FR-DE-02)."""

    FRACTION_OF_PREVIOUS_RND_BUDGET = "fraction_of_previous_rnd_budget"
    PP_OF_REVENUE = "pp_of_revenue"
    FRACTION_OF_HEADCOUNT = "fraction_of_headcount"
    FRACTION_OF_REVENUE = "fraction_of_revenue"
    USD = "usd"


class MagnitudeBase(StrEnum):
    """Company figure a relative magnitude refers to, read at the knowledge cutoff."""

    PREVIOUS_RND_BUDGET = "previous_rnd_budget"
    REVENUE = "revenue"
    HEADCOUNT = "headcount"
    NONE = "none"


class DefaultSourceKind(StrEnum):
    """Where a default comes from. Only the first two are facts."""

    ACCOUNTING_RULE = "accounting_rule"
    STATUTORY_RATE = "statutory_rate"
    DESIGN_DEFAULT = "design_default"
    PLACEHOLDER = "placeholder"


class FinancialStatement(StrEnum):
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"
    BALANCE_SHEET = "balance_sheet"


class DefaultSource(ContractModel):
    kind: DefaultSourceKind
    note: str = Field(min_length=1)


class ValueRange(ContractModel):
    """Inclusive range of decimal values."""

    min: DecimalString
    max: DecimalString

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if Decimal(self.min) >= Decimal(self.max):
            raise ValueError("range min must be below max")
        return self

    def contains(self, value: Decimal) -> bool:
        return Decimal(self.min) <= value <= Decimal(self.max)

    def covers(self, other: "ValueRange") -> bool:
        return self.contains(Decimal(other.min)) and self.contains(Decimal(other.max))


class ParameterSpec(ContractModel):
    """One input of a decision. ``uncertain`` parameters take a distribution."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    unit: ValueUnit
    integer: bool = False
    uncertain: bool = False
    allowed: ValueRange
    planning: ValueRange | None = Field(
        default=None, description="Values outside it are flagged out of distribution."
    )
    step: DecimalString
    default: DecimalString | Distribution
    default_source: DefaultSource

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.planning is not None and not self.allowed.covers(self.planning):
            raise ValueError(f"{self.key}: planning range must lie inside the allowed range")
        if self.uncertain != (not isinstance(self.default, str)):
            raise ValueError(f"{self.key}: uncertain parameters need a distribution default")
        default = self.default
        points = [default] if isinstance(default, str) else distribution_points(default)
        for point in points:
            value = Decimal(point)
            if not self.allowed.contains(value):
                raise ValueError(f"{self.key}: default {point} is outside the allowed range")
            if self.integer and value != value.to_integral_value():
                raise ValueError(f"{self.key}: default must be a whole number")
        return self


class MagnitudeUnitSpec(ContractModel):
    unit: MagnitudeUnit
    label: str = Field(min_length=1, description="Shown after the number, e.g. '% of revenue'.")
    value_unit: ValueUnit
    base: MagnitudeBase
    allowed: ValueRange
    planning: ValueRange | None = None
    step: DecimalString
    default_value: DecimalString

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.planning is not None and not self.allowed.covers(self.planning):
            raise ValueError(f"{self.unit}: planning range must lie inside the allowed range")
        if not self.allowed.contains(Decimal(self.default_value)):
            raise ValueError(f"{self.unit}: default is outside the allowed range")
        return self


class MagnitudeSpec(ContractModel):
    """Size of the decision. Several units mean several different decisions."""

    label: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    units: tuple[MagnitudeUnitSpec, ...] = Field(min_length=1)
    default_unit: MagnitudeUnit | None = Field(
        description="None when the user must choose: the unit changes what the number means."
    )
    default_source: DefaultSource

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        units = [spec.unit for spec in self.units]
        if len(set(units)) != len(units):
            raise ValueError("magnitude units must be unique")
        if self.default_unit is None and len(units) == 1:
            raise ValueError("a single magnitude unit is the default")
        if self.default_unit is not None and self.default_unit not in units:
            raise ValueError("default_unit must be one of the units")
        return self


class ShareMember(ContractModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)


class ShareGroupSpec(ContractModel):
    """Shares that must add up to exactly 100 % (PRD FR-DE-04, docs/07)."""

    key: Literal["financing", "use_of_proceeds"]
    label: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    members: tuple[ShareMember, ...] = Field(min_length=2)
    defaults: tuple[DecimalString, ...]
    default_source: DefaultSource

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if len(self.defaults) != len(self.members):
            raise ValueError(f"{self.key}: one default per member")
        if sum(Decimal(value) for value in self.defaults) != 1:
            raise ValueError(f"{self.key}: default shares must add up to 1")
        return self


class MechanismEffect(ContractModel):
    statement: FinancialStatement
    effect: str = Field(min_length=1)


class InterventionSpec(ContractModel):
    """Definition of one decision type, following the template of docs/16."""

    type: InterventionType
    label: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    magnitude: MagnitudeSpec
    parameters: tuple[ParameterSpec, ...]
    share_group: ShareGroupSpec | None
    lag_quarters: ParameterSpec
    ramp_quarters: ParameterSpec
    mechanism: tuple[MechanismEffect, ...] = Field(min_length=1)
    does_not_mean: str = Field(min_length=1)
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        keys = [parameter.key for parameter in self.parameters]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{self.type}: parameter keys must be unique")
        return self

    def parameter(self, key: str) -> ParameterSpec | None:
        return next((parameter for parameter in self.parameters if parameter.key == key), None)


class InterventionCatalog(ContractModel):
    contracts_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    planning_range_note: str = Field(min_length=1)
    horizon_quarters: ParameterSpec
    default_seed: int = Field(ge=0, le=2**31 - 1)
    sensitivity_max_parameters: int = Field(ge=1)
    sensitivity_points: tuple[int, ...] = Field(min_length=1)
    default_sensitivity_points: int
    interventions: tuple[InterventionSpec, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        types = [spec.type for spec in self.interventions]
        if sorted(types) != sorted(InterventionType):
            raise ValueError("the catalog must define every intervention type exactly once")
        if self.default_sensitivity_points not in self.sensitivity_points:
            raise ValueError("default_sensitivity_points must be one of sensitivity_points")
        return self

    def spec(self, intervention: InterventionType | str) -> InterventionSpec:
        return next(spec for spec in self.interventions if spec.type == intervention)


# Catalog data. Helpers keep the six definitions readable.


def _range(low: str, high: str) -> ValueRange:
    return ValueRange(min=low, max=high)


def _source(kind: DefaultSourceKind, note: str) -> DefaultSource:
    return DefaultSource(kind=kind, note=note)


def _triangular(low: str, mode: str, high: str) -> TriangularRange:
    return TriangularRange(shape="triangular", low=low, mode=mode, high=high)


DESIGN = DefaultSourceKind.DESIGN_DEFAULT
PLACEHOLDER = DefaultSourceKind.PLACEHOLDER
UNSUPPORTED = (
    "Unsupported hypothetical. No causal estimate exists for this decision type yet; "
    "the causal pipeline (Stage 20) studies R&D intensity first (decision D-03)."
)
ONE_BN = "1000000000"


def _financing(cash: str, debt: str, equity: str, note: str) -> ShareGroupSpec:
    return ShareGroupSpec(
        key="financing",
        label="Financing",
        explanation=(
            "How the cash needed for the decision is raised. Shares add up to exactly 100%; "
            "new equity dilutes existing shareholders."
        ),
        members=(
            ShareMember(key="cash", label="Cash on hand"),
            ShareMember(key="debt", label="New debt"),
            ShareMember(key="equity", label="New equity"),
        ),
        defaults=(cash, debt, equity),
        default_source=_source(DESIGN, note),
    )


def _quarters(key: str, label: str, explanation: str, high: str, default: str) -> ParameterSpec:
    return ParameterSpec(
        key=key,
        label=label,
        explanation=explanation,
        unit=ValueUnit.QUARTERS,
        integer=True,
        allowed=_range("0", high),
        step="1",
        default=default,
        default_source=_source(DESIGN, "Typical timing for this kind of decision; adjust it."),
    )


def _lag(high: str, default: str, explanation: str) -> ParameterSpec:
    return _quarters("lag_quarters", "Lag", explanation, high, default)


def _ramp(high: str, default: str, explanation: str) -> ParameterSpec:
    return _quarters("ramp_quarters", "Ramp to full effect", explanation, high, default)


def _new_debt_rate() -> ParameterSpec:
    return ParameterSpec(
        key="new_debt_interest_rate",
        label="Interest rate on new debt",
        explanation="Annual interest rate on the debt raised for this decision.",
        unit=ValueUnit.FRACTION,
        allowed=_range("0", "0.25"),
        planning=_range("0.01", "0.12"),
        step="0.0025",
        default="0.06",
        default_source=_source(
            PLACEHOLDER,
            "Illustrative annual rate. The real rate depends on the market at the decision "
            "date and on the company's credit.",
        ),
    )


RND_CHANGE = InterventionSpec(
    type=InterventionType.RND_CHANGE,
    label="R&D budget change",
    summary="Raise or cut research and development spending.",
    magnitude=MagnitudeSpec(
        label="R&D change",
        explanation=(
            "How much yearly R&D spending changes. A change of the budget and a change of "
            "R&D intensity are different decisions: +40% of a USD 400m budget is USD 160m "
            "a year, while +40 percentage points of a USD 4bn revenue would be USD 1.6bn."
        ),
        units=(
            MagnitudeUnitSpec(
                unit=MagnitudeUnit.FRACTION_OF_PREVIOUS_RND_BUDGET,
                label="% of the previous R&D budget",
                value_unit=ValueUnit.FRACTION,
                base=MagnitudeBase.PREVIOUS_RND_BUDGET,
                allowed=_range("-0.9", "5"),
                planning=_range("-0.5", "1.2"),
                step="0.01",
                default_value="0.2",
            ),
            MagnitudeUnitSpec(
                unit=MagnitudeUnit.PP_OF_REVENUE,
                label="percentage points of revenue",
                value_unit=ValueUnit.PERCENTAGE_POINTS,
                base=MagnitudeBase.REVENUE,
                allowed=_range("-20", "20"),
                planning=_range("-5", "5"),
                step="0.1",
                default_value="1",
            ),
        ),
        default_unit=None,
        default_source=_source(
            DESIGN,
            "A neutral starting value. The unit has no default on purpose: it changes what "
            "the number means.",
        ),
    ),
    parameters=(
        ParameterSpec(
            key="capitalized_fraction",
            label="Share capitalized",
            explanation=(
                "Part of the extra R&D recorded as an asset and depreciated instead of expensed "
                "at once. It moves cost from EBITDA to depreciation; the cash spent is the same."
            ),
            unit=ValueUnit.FRACTION,
            allowed=_range("0", "1"),
            planning=_range("0", "0.5"),
            step="0.05",
            default="0",
            default_source=_source(
                DefaultSourceKind.ACCOUNTING_RULE,
                "US GAAP (ASC 730) expenses most R&D as incurred. Software development and "
                "some acquired R&D are exceptions.",
            ),
        ),
        ParameterSpec(
            key="adoption_delay_quarters",
            label="Adoption delay",
            explanation=(
                "Time from the spending to the first revenue it could produce. The cost hits "
                "EBIT at once; any revenue comes later and is uncertain."
            ),
            unit=ValueUnit.QUARTERS,
            uncertain=True,
            allowed=_range("0", "40"),
            planning=_range("0", "16"),
            step="1",
            default=_triangular("4", "8", "12"),
            default_source=_source(
                PLACEHOLDER,
                "Placeholder until the causal study (Stage 20) estimates how long R&D takes to "
                "reach revenue.",
            ),
        ),
    ),
    share_group=_financing("1", "0", "0", "Funded from cash on hand."),
    lag_quarters=_lag("12", "0", "Quarters from the effective date until spending changes."),
    ramp_quarters=_ramp("20", "2", "Quarters until spending reaches the new level."),
    mechanism=(
        MechanismEffect(
            statement=FinancialStatement.INCOME_STATEMENT,
            effect=(
                "R&D expense changes by the incremental spending, minus any capitalized share, "
                "so EBIT and EBITDA move by the same amount from the effective date."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.CASH_FLOW,
            effect=(
                "Operating cash flow changes by the full spending; a capitalized share is "
                "reported in investing cash flow instead."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.BALANCE_SHEET,
            effect=(
                "Cash falls, or debt or equity rises, by the funded amount. A capitalized share "
                "becomes an intangible asset."
            ),
        ),
    ),
    does_not_mean=(
        "Higher R&D does not guarantee more revenue. Any revenue effect is an assumption with "
        "a delay, not an observed return."
    ),
    evidence=UNSUPPORTED,
)

WORKFORCE_RESTRUCTURE = InterventionSpec(
    type=InterventionType.WORKFORCE_RESTRUCTURE,
    label="Workforce restructuring",
    summary="Reduce or grow headcount.",
    magnitude=MagnitudeSpec(
        label="Headcount change",
        explanation=(
            "Change of headcount as a share of current employees. −15% means 15 of every 100 "
            "employees leave; it does not mean operating costs fall by 15%."
        ),
        units=(
            MagnitudeUnitSpec(
                unit=MagnitudeUnit.FRACTION_OF_HEADCOUNT,
                label="% of headcount",
                value_unit=ValueUnit.FRACTION,
                base=MagnitudeBase.HEADCOUNT,
                allowed=_range("-0.6", "0.5"),
                planning=_range("-0.25", "0.2"),
                step="0.01",
                default_value="-0.1",
            ),
        ),
        default_unit=MagnitudeUnit.FRACTION_OF_HEADCOUNT,
        default_source=_source(DESIGN, "A neutral starting value for the form."),
    ),
    parameters=(
        ParameterSpec(
            key="payroll_to_revenue",
            label="Payroll as a share of revenue",
            explanation=(
                "Turns a headcount share into dollars. Payroll means wages, salaries and "
                "benefits of all employees."
            ),
            unit=ValueUnit.FRACTION,
            allowed=_range("0.01", "0.9"),
            planning=_range("0.05", "0.5"),
            step="0.01",
            default="0.25",
            default_source=_source(
                PLACEHOLDER,
                "Total payroll is not in the demo data. Replace it with the company's own "
                "figure when known.",
            ),
        ),
        ParameterSpec(
            key="one_off_cost_months",
            label="One-off cost per affected employee",
            explanation=(
                "Severance and restructuring charges for a reduction, or hiring and onboarding "
                "costs for an increase, in months of salary."
            ),
            unit=ValueUnit.MONTHS_OF_SALARY,
            uncertain=True,
            allowed=_range("0", "24"),
            planning=_range("0", "12"),
            step="0.5",
            default=_triangular("2", "4", "8"),
            default_source=_source(
                PLACEHOLDER,
                "Severance depends on country, contract and seniority; this range is a "
                "placeholder.",
            ),
        ),
        ParameterSpec(
            key="savings_realization",
            label="Payroll change realized",
            explanation=(
                "Share of the gross payroll change that shows up in costs, after retention "
                "bonuses, contractors and rehiring."
            ),
            unit=ValueUnit.FRACTION,
            uncertain=True,
            allowed=_range("0", "1"),
            planning=_range("0.3", "1"),
            step="0.05",
            default=_triangular("0.5", "0.7", "0.9"),
            default_source=_source(PLACEHOLDER, "No estimate exists yet; placeholder range."),
        ),
        ParameterSpec(
            key="productivity_loss",
            label="Productivity loss",
            explanation=(
                "Temporary loss of output among remaining employees during the ramp: lost "
                "knowledge, handovers, morale. It lowers revenue capacity."
            ),
            unit=ValueUnit.FRACTION,
            uncertain=True,
            allowed=_range("0", "0.5"),
            planning=_range("0", "0.2"),
            step="0.01",
            default=_triangular("0", "0.03", "0.1"),
            default_source=_source(PLACEHOLDER, "No estimate exists yet; placeholder range."),
        ),
    ),
    share_group=_financing("1", "0", "0", "One-off costs paid from cash on hand."),
    lag_quarters=_lag("8", "1", "Quarters from the effective date until headcount changes."),
    ramp_quarters=_ramp("12", "2", "Quarters until the new headcount is fully in place."),
    mechanism=(
        MechanismEffect(
            statement=FinancialStatement.INCOME_STATEMENT,
            effect=(
                "Payroll cost changes by the realized share of the gross change. A one-off "
                "restructuring charge is recorded when the plan is committed."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.CASH_FLOW,
            effect="Severance is paid in cash; recurring savings or costs follow payroll.",
        ),
        MechanismEffect(
            statement=FinancialStatement.BALANCE_SHEET,
            effect="A restructuring liability is recognized and then paid, lowering cash.",
        ),
    ),
    does_not_mean=(
        "Cutting 15% of staff does not cut operating costs by 15%. Savings are partial, arrive "
        "with a delay and come with a one-off charge and execution risk."
    ),
    evidence=UNSUPPORTED,
)

ACQUISITION = InterventionSpec(
    type=InterventionType.ACQUISITION,
    label="Acquisition",
    summary="Buy another company and fund the deal.",
    magnitude=MagnitudeSpec(
        label="Purchase price",
        explanation=(
            "Enterprise value paid for the target. The buyer does not gain the price as value: "
            "what matters is what the target earns, the synergies and the cost of funding."
        ),
        units=(
            MagnitudeUnitSpec(
                unit=MagnitudeUnit.USD,
                label="USD",
                value_unit=ValueUnit.USD,
                base=MagnitudeBase.NONE,
                allowed=_range("1000000", "1000000000000"),
                planning=_range("10000000", "50000000000"),
                step="1000000",
                default_value=ONE_BN,
            ),
        ),
        default_unit=MagnitudeUnit.USD,
        default_source=_source(DESIGN, "An illustrative deal size for the form."),
    ),
    parameters=(
        ParameterSpec(
            key="target_revenue",
            label="Target revenue per year",
            explanation="Revenue the target adds per year after closing.",
            unit=ValueUnit.USD,
            allowed=_range("0", "1000000000000"),
            step="1000000",
            default="400000000",
            default_source=_source(
                PLACEHOLDER, "Illustrative target. Enter the target's reported revenue."
            ),
        ),
        ParameterSpec(
            key="target_ebitda_margin",
            label="Target EBITDA margin",
            explanation="EBITDA of the target as a share of its revenue.",
            unit=ValueUnit.FRACTION,
            allowed=_range("-1", "0.8"),
            planning=_range("-0.2", "0.5"),
            step="0.01",
            default="0.15",
            default_source=_source(PLACEHOLDER, "Illustrative margin. Enter the target's own."),
        ),
        ParameterSpec(
            key="deal_cost_fraction",
            label="Deal costs",
            explanation=(
                "Advisory, legal and financing fees as a share of the purchase price. They are "
                "expensed and funded together with the price."
            ),
            unit=ValueUnit.FRACTION,
            allowed=_range("0", "0.1"),
            planning=_range("0", "0.05"),
            step="0.005",
            default="0.02",
            default_source=_source(PLACEHOLDER, "Placeholder share of the price."),
        ),
        ParameterSpec(
            key="integration_cost_fraction",
            label="Integration cost",
            explanation=(
                "One-off cost to combine systems, sites and teams, as a share of the purchase "
                "price, spread over the ramp."
            ),
            unit=ValueUnit.FRACTION,
            uncertain=True,
            allowed=_range("0", "0.3"),
            planning=_range("0", "0.15"),
            step="0.005",
            default=_triangular("0.02", "0.05", "0.1"),
            default_source=_source(PLACEHOLDER, "No estimate exists yet; placeholder range."),
        ),
        ParameterSpec(
            key="cost_synergy_fraction",
            label="Cost synergies",
            explanation=(
                "Yearly cost savings at full integration, as a share of target revenue. They "
                "arrive at the end of the ramp, if at all."
            ),
            unit=ValueUnit.FRACTION,
            uncertain=True,
            allowed=_range("0", "0.3"),
            planning=_range("0", "0.1"),
            step="0.005",
            default=_triangular("0", "0.03", "0.06"),
            default_source=_source(PLACEHOLDER, "No estimate exists yet; placeholder range."),
        ),
        ParameterSpec(
            key="completion_probability",
            label="Chance the deal closes",
            explanation=(
                "Probability that the deal completes, for example after antitrust review. If "
                "it fails, deal costs are still spent."
            ),
            unit=ValueUnit.FRACTION,
            allowed=_range("0.05", "1"),
            planning=_range("0.5", "1"),
            step="0.05",
            default="0.9",
            default_source=_source(PLACEHOLDER, "Placeholder probability."),
        ),
        _new_debt_rate(),
    ),
    share_group=_financing("0.5", "0.5", "0", "An illustrative even split of cash and debt."),
    lag_quarters=_lag("8", "2", "Quarters from the effective date until the deal closes."),
    ramp_quarters=_ramp("20", "8", "Quarters of integration until synergies are complete."),
    mechanism=(
        MechanismEffect(
            statement=FinancialStatement.INCOME_STATEMENT,
            effect=(
                "Target revenue and EBITDA are added from closing. Deal and integration costs "
                "are expensed. Interest on new debt and amortization of acquired intangibles "
                "lower net income."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.CASH_FLOW,
            effect=(
                "The cash part of the price and the deal costs flow out at closing; new debt "
                "flows in. Synergies improve operating cash flow after the ramp."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.BALANCE_SHEET,
            effect=(
                "Goodwill and acquired intangibles appear. Debt rises by the debt share; new "
                "equity dilutes existing shareholders."
            ),
        ),
    ),
    does_not_mean=(
        "Paying USD 1bn does not add USD 1bn of value. Value depends on the target's cash "
        "flows, synergies, integration cost and the price of funding."
    ),
    evidence=UNSUPPORTED,
)

DIVESTITURE = InterventionSpec(
    type=InterventionType.DIVESTITURE,
    label="Divestiture or segment exit",
    summary="Sell or close part of the business.",
    magnitude=MagnitudeSpec(
        label="Revenue divested",
        explanation="Share of the company's revenue that leaves with the sold or closed unit.",
        units=(
            MagnitudeUnitSpec(
                unit=MagnitudeUnit.FRACTION_OF_REVENUE,
                label="% of revenue",
                value_unit=ValueUnit.FRACTION,
                base=MagnitudeBase.REVENUE,
                allowed=_range("0.01", "0.9"),
                planning=_range("0.01", "0.5"),
                step="0.01",
                default_value="0.1",
            ),
        ),
        default_unit=MagnitudeUnit.FRACTION_OF_REVENUE,
        default_source=_source(DESIGN, "A neutral starting value for the form."),
    ),
    parameters=(
        ParameterSpec(
            key="segment_ebitda_margin",
            label="EBITDA margin of the unit",
            explanation=(
                "EBITDA margin of the unit that leaves. A negative margin means a loss-making "
                "unit; exiting it raises the group margin."
            ),
            unit=ValueUnit.FRACTION,
            allowed=_range("-1", "0.8"),
            planning=_range("-0.3", "0.5"),
            step="0.01",
            default="0.05",
            default_source=_source(
                PLACEHOLDER,
                "Segment figures are not in the demo data; segment reporting arrives with XBRL "
                "normalization (Stage 11).",
            ),
        ),
        ParameterSpec(
            key="disposal_proceeds",
            label="Sale proceeds",
            explanation="Cash received from a buyer. Zero means the unit is closed.",
            unit=ValueUnit.USD,
            allowed=_range("0", "1000000000000"),
            step="1000000",
            default="0",
            default_source=_source(DESIGN, "Zero: a closure without a buyer."),
        ),
        ParameterSpec(
            key="separation_cost_fraction",
            label="Separation cost",
            explanation=(
                "One-off cost to separate or close the unit (contracts, systems, sites), as a "
                "share of the unit's yearly revenue."
            ),
            unit=ValueUnit.FRACTION,
            allowed=_range("0", "0.5"),
            planning=_range("0", "0.1"),
            step="0.005",
            default="0.03",
            default_source=_source(PLACEHOLDER, "Placeholder share."),
        ),
        ParameterSpec(
            key="stranded_cost_fraction",
            label="Stranded overhead",
            explanation=(
                "Shared overhead that stays with the company after the unit leaves, as a share "
                "of the overhead the unit carried."
            ),
            unit=ValueUnit.FRACTION,
            uncertain=True,
            allowed=_range("0", "1"),
            planning=_range("0", "0.6"),
            step="0.05",
            default=_triangular("0.1", "0.25", "0.4"),
            default_source=_source(PLACEHOLDER, "No estimate exists yet; placeholder range."),
        ),
        ParameterSpec(
            key="tax_rate_on_gain",
            label="Tax rate on the gain",
            explanation="Tax paid on the gain from a sale.",
            unit=ValueUnit.FRACTION,
            allowed=_range("0", "0.5"),
            step="0.01",
            default="0.21",
            default_source=_source(
                DefaultSourceKind.STATUTORY_RATE,
                "US federal corporate income tax rate since 2018 (Tax Cuts and Jobs Act). State "
                "taxes and the tax basis of the unit are not modelled.",
            ),
        ),
    ),
    share_group=ShareGroupSpec(
        key="use_of_proceeds",
        label="Use of proceeds",
        explanation="Where the net proceeds go. Shares add up to exactly 100%.",
        members=(
            ShareMember(key="debt_paydown", label="Pay down debt"),
            ShareMember(key="cash_retained", label="Keep as cash"),
            ShareMember(key="shareholder_distribution", label="Return to shareholders"),
        ),
        defaults=("0.5", "0.5", "0"),
        default_source=_source(DESIGN, "An illustrative even split."),
    ),
    lag_quarters=_lag("8", "2", "Quarters from the effective date until the unit leaves."),
    ramp_quarters=_ramp("12", "2", "Quarters until stranded costs settle."),
    mechanism=(
        MechanismEffect(
            statement=FinancialStatement.INCOME_STATEMENT,
            effect=(
                "Revenue and EBITDA of the unit leave; stranded overhead stays. A gain or loss "
                "on sale and separation costs are one-off items."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.CASH_FLOW,
            effect=(
                "Proceeds flow in, less tax on the gain and separation costs. The unit's "
                "operating cash flow stops."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.BALANCE_SHEET,
            effect=(
                "The unit's assets and liabilities leave. Proceeds pay down debt, stay as cash "
                "or go to shareholders."
            ),
        ),
    ),
    does_not_mean=(
        "Selling a unit with 10% of revenue does not cut costs by 10%. Shared overhead stays "
        "behind, and margins improve only if the unit earned less than the rest."
    ),
    evidence=UNSUPPORTED,
)

CAPEX_EXPANSION = InterventionSpec(
    type=InterventionType.CAPEX_EXPANSION,
    label="CAPEX expansion",
    summary="Invest in new capacity.",
    magnitude=MagnitudeSpec(
        label="Investment",
        explanation="Total capital expenditure of the program.",
        units=(
            MagnitudeUnitSpec(
                unit=MagnitudeUnit.USD,
                label="USD",
                value_unit=ValueUnit.USD,
                base=MagnitudeBase.NONE,
                allowed=_range("1000000", "500000000000"),
                planning=_range("10000000", "20000000000"),
                step="1000000",
                default_value="500000000",
            ),
        ),
        default_unit=MagnitudeUnit.USD,
        default_source=_source(DESIGN, "An illustrative program size for the form."),
    ),
    parameters=(
        ParameterSpec(
            key="capacity_increase",
            label="Capacity increase",
            explanation=(
                "Extra capacity as a share of current capacity. Capacity is not revenue: "
                "revenue follows only as far as the new capacity is used and sold."
            ),
            unit=ValueUnit.FRACTION,
            allowed=_range("0.01", "2"),
            planning=_range("0.01", "0.5"),
            step="0.01",
            default="0.3",
            default_source=_source(
                DESIGN, "Example from the scenario library (docs/16: new plant, +30% capacity)."
            ),
        ),
        ParameterSpec(
            key="useful_life_years",
            label="Useful life",
            explanation="Years over which the investment is depreciated, straight-line.",
            unit=ValueUnit.YEARS,
            integer=True,
            allowed=_range("3", "50"),
            planning=_range("5", "40"),
            step="1",
            default="20",
            default_source=_source(
                PLACEHOLDER, "Illustrative life; buildings last longer than equipment."
            ),
        ),
        ParameterSpec(
            key="utilization",
            label="Utilization after the ramp",
            explanation="Share of the new capacity in use. Idle capacity still depreciates.",
            unit=ValueUnit.FRACTION,
            uncertain=True,
            allowed=_range("0", "1"),
            planning=_range("0.3", "1"),
            step="0.05",
            default=_triangular("0.5", "0.75", "0.9"),
            default_source=_source(PLACEHOLDER, "No estimate exists yet; placeholder range."),
        ),
        _new_debt_rate(),
    ),
    share_group=_financing("0.5", "0.5", "0", "An illustrative even split of cash and debt."),
    lag_quarters=_lag("16", "4", "Quarters of construction before the capacity is ready."),
    ramp_quarters=_ramp("20", "4", "Quarters until utilization reaches its level."),
    mechanism=(
        MechanismEffect(
            statement=FinancialStatement.INCOME_STATEMENT,
            effect=(
                "Depreciation starts when the asset is in use. Revenue and costs from the new "
                "capacity follow utilization."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.CASH_FLOW,
            effect=(
                "Investing cash flow falls by the investment during construction, so free cash "
                "flow drops before any return."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.BALANCE_SHEET,
            effect="Property, plant and equipment rises; cash falls or debt rises.",
        ),
    ),
    does_not_mean=(
        "+30% capacity does not mean +30% revenue. Revenue depends on demand, price and the "
        "ramp; idle capacity is a cost."
    ),
    evidence=UNSUPPORTED,
)

DEBT_REFINANCE = InterventionSpec(
    type=InterventionType.DEBT_REFINANCE,
    label="Debt refinancing",
    summary="Replace existing debt with new debt.",
    magnitude=MagnitudeSpec(
        label="Amount refinanced",
        explanation="Principal of existing debt replaced by new debt.",
        units=(
            MagnitudeUnitSpec(
                unit=MagnitudeUnit.USD,
                label="USD",
                value_unit=ValueUnit.USD,
                base=MagnitudeBase.NONE,
                allowed=_range("1000000", "500000000000"),
                planning=_range("10000000", "20000000000"),
                step="1000000",
                default_value=ONE_BN,
            ),
        ),
        default_unit=MagnitudeUnit.USD,
        default_source=_source(DESIGN, "An illustrative amount for the form."),
    ),
    parameters=(
        ParameterSpec(
            key="current_interest_rate",
            label="Current interest rate",
            explanation="Annual rate on the debt that is replaced.",
            unit=ValueUnit.FRACTION,
            allowed=_range("0", "0.3"),
            planning=_range("0.005", "0.15"),
            step="0.0025",
            default="0.07",
            default_source=_source(
                PLACEHOLDER,
                "Debt terms are not in the demo data. Enter the rate of the debt being replaced.",
            ),
        ),
        ParameterSpec(
            key="new_interest_rate",
            label="New interest rate",
            explanation=(
                "Annual rate on the new debt. Market rates at the decision date are uncertain."
            ),
            unit=ValueUnit.FRACTION,
            uncertain=True,
            allowed=_range("0", "0.3"),
            planning=_range("0.005", "0.15"),
            step="0.0025",
            default=_triangular("0.045", "0.055", "0.07"),
            default_source=_source(PLACEHOLDER, "Placeholder range."),
        ),
        ParameterSpec(
            key="new_maturity_years",
            label="New maturity",
            explanation="Years until the new debt must be repaid.",
            unit=ValueUnit.YEARS,
            integer=True,
            allowed=_range("1", "40"),
            planning=_range("2", "15"),
            step="1",
            default="7",
            default_source=_source(DESIGN, "A common maturity for corporate bonds; adjust."),
        ),
        ParameterSpec(
            key="refinancing_fee_fraction",
            label="Fees",
            explanation="Fees and any prepayment penalty, as a share of the amount refinanced.",
            unit=ValueUnit.FRACTION,
            allowed=_range("0", "0.05"),
            planning=_range("0", "0.02"),
            step="0.0025",
            default="0.01",
            default_source=_source(PLACEHOLDER, "Placeholder share."),
        ),
    ),
    share_group=None,
    lag_quarters=_lag("4", "0", "Quarters from the effective date until the new debt is drawn."),
    ramp_quarters=_ramp("4", "0", "Quarters until all old debt is replaced."),
    mechanism=(
        MechanismEffect(
            statement=FinancialStatement.INCOME_STATEMENT,
            effect=(
                "Interest expense changes by the amount times the rate difference. Fees and any "
                "write-off of old issuance costs are one-off."
            ),
        ),
        MechanismEffect(
            statement=FinancialStatement.CASH_FLOW,
            effect="Interest payments change; fees are paid at closing. Principal is replaced.",
        ),
        MechanismEffect(
            statement=FinancialStatement.BALANCE_SHEET,
            effect="Debt stays about the same; its rate and maturity change.",
        ),
    ),
    does_not_mean=(
        "A lower rate does not create value by itself if fees, a shorter maturity or covenants "
        "offset it. Past rates were set by the market, not chosen by the company."
    ),
    evidence=UNSUPPORTED,
)

CATALOG = InterventionCatalog(
    contracts_version=CONTRACTS_VERSION,
    planning_range_note=(
        "Planning ranges are design defaults, not measured historical ranges. Stage 14 replaces "
        "them with ranges measured on real data. A value outside the planning range is flagged "
        "out of distribution: any result for it would be fictional exploratory."
    ),
    horizon_quarters=ParameterSpec(
        key="horizon_quarters",
        label="Horizon",
        explanation="Quarters after the knowledge cutoff that a run will cover.",
        unit=ValueUnit.QUARTERS,
        integer=True,
        allowed=_range("4", "40"),
        planning=_range("4", "20"),
        step="1",
        default="20",
        default_source=_source(DESIGN, "Five years, as in the API example of docs/09."),
    ),
    default_seed=20261027,
    sensitivity_max_parameters=3,
    sensitivity_points=(3, 5, 7),
    default_sensitivity_points=5,
    interventions=(
        RND_CHANGE,
        WORKFORCE_RESTRUCTURE,
        ACQUISITION,
        DIVESTITURE,
        CAPEX_EXPANSION,
        DEBT_REFINANCE,
    ),
)
