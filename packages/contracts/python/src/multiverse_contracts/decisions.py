"""A management decision and the scenario draft around it (PRD FR-DE, docs/07, docs/09).

Each decision type has its own model with exactly the fields of its catalog entry
(``interventions.CATALOG``). The validators read ranges from the catalog, so the
contract, the web form and the future ``POST /api/v1/scenarios/validate`` share one
definition. Rule violations carry a stable code in brackets, for example
``[shares_sum]``; the web validator reports the same codes (shared fixtures).
"""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from multiverse_contracts.distributions import (
    Distribution,
    FixedValue,
    TriangularRange,
    UniformRange,
    distribution_points,
)
from multiverse_contracts.interventions import (
    CATALOG,
    InterventionSpec,
    MagnitudeUnit,
    ParameterSpec,
)
from multiverse_contracts.primitives import ContractModel, DataOrigin, DecimalString

_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def rule_error(code: str, path: str, message: str) -> ValueError:
    """A contract rule violation with a stable code and the path of the offending field."""
    return ValueError(f"[{code}] {path}: {message}")


def add_quarters(start: date, quarters: int) -> date:
    """Same day ``quarters`` * 3 months later, clamped to the end of a shorter month."""
    months = start.month - 1 + 3 * quarters
    year, month = start.year + months // 12, months % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


class Magnitude(ContractModel):
    """Size of a decision. The unit is required: 0.4 alone could mean four different things."""

    value: DecimalString
    unit: MagnitudeUnit


class Timing(ContractModel):
    """When the decision is announced, takes effect, and how long its effect takes."""

    announcement_date: date
    effective_date: date
    lag_quarters: int = Field(description="Quarters from the effective date to the first effect.")
    ramp_quarters: int = Field(description="Quarters from the start until the full effect.")


class FundingMix(ContractModel):
    """Shares of the funding need; they add up to exactly 1."""

    cash: DecimalString
    debt: DecimalString
    equity: DecimalString


class ProceedsAllocation(ContractModel):
    """Shares of the net proceeds of a divestiture; they add up to exactly 1."""

    debt_paydown: DecimalString
    cash_retained: DecimalString
    shareholder_distribution: DecimalString


def _check_number(value: str | int, spec: ParameterSpec, path: str) -> None:
    if not spec.allowed.contains(Decimal(str(value))):
        raise rule_error(
            "out_of_range",
            path,
            f"{value} is outside the allowed range {spec.allowed.min} to {spec.allowed.max}",
        )


def _check_distribution(
    distribution: FixedValue | UniformRange | TriangularRange, spec: ParameterSpec, path: str
) -> None:
    names = {"fixed": ("value",), "uniform": ("low", "high"), "triangular": ("low", "mode", "high")}
    points = distribution_points(distribution)
    for name, point in zip(names[distribution.shape], points, strict=True):
        _check_number(point, spec, f"{path}.{name}")
    values = [Decimal(point) for point in points]
    if values != sorted(values) or (len(values) > 1 and values[0] == values[-1]):
        raise rule_error(
            "distribution_order", path, "values must satisfy low <= mode <= high and low < high"
        )


def _check_decision(decision: "DecisionModel") -> None:
    spec: InterventionSpec = CATALOG.spec(decision.type)

    unit_spec = next((u for u in spec.magnitude.units if u.unit == decision.magnitude.unit), None)
    if unit_spec is None:
        raise rule_error(
            "unit_not_allowed",
            "decision.magnitude.unit",
            f"'{decision.magnitude.unit}' is not a unit of {decision.type}",
        )
    magnitude = Decimal(decision.magnitude.value)
    if not unit_spec.allowed.contains(magnitude):
        raise rule_error(
            "out_of_range",
            "decision.magnitude.value",
            f"{magnitude} is outside the allowed range "
            f"{unit_spec.allowed.min} to {unit_spec.allowed.max}",
        )
    if magnitude == 0:
        raise rule_error(
            "zero_magnitude", "decision.magnitude.value", "a decision of size 0 is the baseline"
        )

    for timing_spec in (spec.lag_quarters, spec.ramp_quarters):
        value = getattr(decision.timing, timing_spec.key)
        _check_number(value, timing_spec, f"decision.timing.{timing_spec.key}")

    for parameter in spec.parameters:
        value = getattr(decision, parameter.key)
        path = f"decision.{parameter.key}"
        if parameter.uncertain:
            _check_distribution(value, parameter, path)
        else:
            _check_number(value, parameter, path)

    group = spec.share_group
    if group is not None:
        shares = getattr(decision, group.key)
        total = Decimal(0)
        for member in group.members:
            share = Decimal(getattr(shares, member.key))
            if not 0 <= share <= 1:
                raise rule_error(
                    "out_of_range", f"decision.{group.key}.{member.key}", "a share is 0 to 100%"
                )
            total += share
        if total != 1:
            raise rule_error(
                "shares_sum",
                f"decision.{group.key}",
                f"shares add up to {total * 100:f}%; they must add up to exactly 100%",
            )
        rate = getattr(decision, "new_debt_interest_rate", None)
        if Decimal(getattr(shares, "debt", "0")) > 0 and rate is not None and Decimal(rate) == 0:
            raise rule_error(
                "rate_required",
                "decision.new_debt_interest_rate",
                "new debt needs an interest rate above 0",
            )


class _DecisionBase(ContractModel):
    magnitude: Magnitude
    timing: Timing

    @model_validator(mode="after")
    def _within_catalog(self) -> Self:
        _check_decision(self)  # type: ignore[arg-type]  # every subclass is a DecisionModel
        return self


class RndChange(_DecisionBase):
    type: Literal["rnd_change"]
    capitalized_fraction: DecimalString
    adoption_delay_quarters: Distribution
    financing: FundingMix


class WorkforceRestructure(_DecisionBase):
    type: Literal["workforce_restructure"]
    payroll_to_revenue: DecimalString
    one_off_cost_months: Distribution
    savings_realization: Distribution
    productivity_loss: Distribution
    financing: FundingMix


class Acquisition(_DecisionBase):
    type: Literal["acquisition"]
    target_revenue: DecimalString
    target_ebitda_margin: DecimalString
    deal_cost_fraction: DecimalString
    integration_cost_fraction: Distribution
    cost_synergy_fraction: Distribution
    completion_probability: DecimalString
    new_debt_interest_rate: DecimalString
    financing: FundingMix


class Divestiture(_DecisionBase):
    type: Literal["divestiture"]
    segment_ebitda_margin: DecimalString
    disposal_proceeds: DecimalString
    separation_cost_fraction: DecimalString
    stranded_cost_fraction: Distribution
    tax_rate_on_gain: DecimalString
    use_of_proceeds: ProceedsAllocation


class CapexExpansion(_DecisionBase):
    type: Literal["capex_expansion"]
    capacity_increase: DecimalString
    useful_life_years: int
    utilization: Distribution
    new_debt_interest_rate: DecimalString
    financing: FundingMix


class DebtRefinance(_DecisionBase):
    type: Literal["debt_refinance"]
    current_interest_rate: DecimalString
    new_interest_rate: Distribution
    new_maturity_years: int
    refinancing_fee_fraction: DecimalString


DecisionModel = (
    RndChange | WorkforceRestructure | Acquisition | Divestiture | CapexExpansion | DebtRefinance
)
Decision = Annotated[DecisionModel, Field(discriminator="type")]

DECISION_MODELS: dict[str, type[_DecisionBase]] = {
    "rnd_change": RndChange,
    "workforce_restructure": WorkforceRestructure,
    "acquisition": Acquisition,
    "divestiture": Divestiture,
    "capex_expansion": CapexExpansion,
    "debt_refinance": DebtRefinance,
}


class SensitivitySettings(ContractModel):
    """One-at-a-time sensitivity over uncertain parameters of the decision."""

    parameters: tuple[str, ...] = ()
    points: int = CATALOG.default_sensitivity_points


class ScenarioDraft(ContractModel):
    """A decision for one company at one knowledge cutoff, ready to validate and run.

    ``as_of`` is a date: the knowledge cutoff is the end of that day in UTC, as in the
    dossier (ADR-0002). A decision made at the cutoff can be announced on the cutoff
    day at the earliest.
    """

    contracts_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    company_id: str = Field(pattern=_UUID)
    as_of: date
    data_origin: DataOrigin
    horizon_quarters: int
    seed: int = Field(ge=0, le=2**31 - 1)
    decision: Decision
    sensitivity: SensitivitySettings = SensitivitySettings()

    @model_validator(mode="after")
    def _check_scenario(self) -> Self:
        _check_number(self.horizon_quarters, CATALOG.horizon_quarters, "horizon_quarters")

        timing = self.decision.timing
        if timing.announcement_date < self.as_of:
            raise rule_error(
                "announcement_before_cutoff",
                "decision.timing.announcement_date",
                f"a decision made at the cutoff {self.as_of} cannot be announced before it",
            )
        if timing.effective_date < timing.announcement_date:
            raise rule_error(
                "effective_before_announcement",
                "decision.timing.effective_date",
                "the effective date cannot come before the announcement",
            )
        horizon_end = add_quarters(self.as_of, self.horizon_quarters)
        if timing.effective_date >= horizon_end:
            raise rule_error(
                "effect_after_horizon",
                "decision.timing.effective_date",
                f"the effective date must fall before the end of the horizon, {horizon_end}",
            )
        if add_quarters(timing.effective_date, timing.lag_quarters) >= horizon_end:
            raise rule_error(
                "effect_after_horizon",
                "decision.timing.lag_quarters",
                f"the effect would start after the end of the horizon, {horizon_end}",
            )

        self._check_sensitivity()
        return self

    def _check_sensitivity(self) -> None:
        settings = self.sensitivity
        path = "sensitivity.parameters"
        if settings.points not in CATALOG.sensitivity_points:
            raise rule_error(
                "sensitivity_points", "sensitivity.points", "use 3, 5 or 7 points per parameter"
            )
        if len(settings.parameters) > CATALOG.sensitivity_max_parameters:
            raise rule_error(
                "sensitivity_too_many",
                path,
                f"choose at most {CATALOG.sensitivity_max_parameters} parameters",
            )
        if len(set(settings.parameters)) != len(settings.parameters):
            raise rule_error("sensitivity_duplicate", path, "each parameter at most once")
        spec = CATALOG.spec(self.decision.type)
        for key in settings.parameters:
            parameter = spec.parameter(key)
            if parameter is None or not parameter.uncertain:
                raise rule_error(
                    "sensitivity_unknown", path, f"'{key}' is not an uncertain parameter"
                )
            if getattr(self.decision, key).shape == "fixed":
                raise rule_error(
                    "sensitivity_fixed", path, f"'{key}' has a fixed value; give it a range first"
                )
