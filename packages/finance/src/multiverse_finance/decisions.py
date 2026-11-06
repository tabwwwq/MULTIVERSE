"""From a decision of the contract to a plan the engine can book.

The contract holds ranges; a plan holds one realized path. Here every uncertain parameter takes
its central value and the deal closes. Stage 22 draws them instead and passes the terms directly.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from multiverse_contracts.decisions import (
    Acquisition,
    CapexExpansion,
    DebtRefinance,
    DecisionModel,
    Divestiture,
    FundingMix,
    RndChange,
    WorkforceRestructure,
)
from multiverse_contracts.distributions import central_value
from multiverse_contracts.interventions import MagnitudeUnit
from multiverse_finance.exact import QUARTERS_PER_YEAR, ZERO, FinanceError, exact
from multiverse_finance.interventions import (
    AcquisitionTerms,
    CapexTerms,
    DivestitureTerms,
    Funding,
    RefinanceTerms,
    RndTerms,
    Timing,
    WorkforceTerms,
    acquisition,
    capex_expansion,
    debt_refinance,
    divestiture,
    rnd_change,
    workforce_restructure,
)
from multiverse_finance.ledger import Plan
from multiverse_finance.model import Baseline

RATE_TOLERANCE = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class Accounting:
    """What the decision form does not ask. Placeholders until measured, like its defaults."""

    development_life_years: int = 5
    acquired_ppe_share: Decimal = Decimal("0.15")
    acquired_intangibles_share: Decimal = Decimal("0.25")
    acquired_intangibles_life_years: int = 10


def quarter_of(base_date: date, day: date) -> int:
    """The quarter of ``day``: quarter 1 starts the day after the base date.

    The base date itself counts as quarter 1: a decision taken at the cutoff acts in the next
    quarter at the earliest.
    """
    if day < base_date:
        raise FinanceError("before_base_date", "timing.effective_date", f"{day} < {base_date}")
    first = base_date + timedelta(days=1)
    months = (day.year - first.year) * 12 + day.month - first.month
    if day.day < first.day:
        months -= 1
    return max(months, 0) // 3 + 1


def _timing(decision: DecisionModel, base_date: date) -> Timing:
    return Timing(
        quarter_of(base_date, decision.timing.effective_date),
        decision.timing.lag_quarters,
        decision.timing.ramp_quarters,
    )


def _funding(mix: FundingMix) -> Funding:
    return Funding(Decimal(mix.cash), Decimal(mix.debt), Decimal(mix.equity))


def _rnd(decision: RndChange, baseline: Baseline, accounting: Accounting) -> Plan:
    value = Decimal(decision.magnitude.value)
    relative = decision.magnitude.unit is MagnitudeUnit.FRACTION_OF_PREVIOUS_RND_BUDGET
    terms = RndTerms(
        timing=_timing(decision, baseline.base_date),
        fraction_of_budget=value if relative else None,
        points_of_revenue=None if relative else value,
        capitalized_fraction=Decimal(decision.capitalized_fraction),
        amortization_quarters=accounting.development_life_years * QUARTERS_PER_YEAR,
        adoption_delay_quarters=int(central_value(decision.adoption_delay_quarters)),
        funding=_funding(decision.financing),
    )
    return rnd_change(baseline, terms)


def _workforce(decision: WorkforceRestructure, baseline: Baseline) -> Plan:
    terms = WorkforceTerms(
        timing=_timing(decision, baseline.base_date),
        headcount_change=Decimal(decision.magnitude.value),
        payroll_to_revenue=Decimal(decision.payroll_to_revenue),
        one_off_cost_months=central_value(decision.one_off_cost_months),
        savings_realization=central_value(decision.savings_realization),
        productivity_loss=central_value(decision.productivity_loss),
        funding=_funding(decision.financing),
    )
    return workforce_restructure(baseline, terms)


def _acquisition(
    decision: Acquisition, baseline: Baseline, accounting: Accounting, completed: bool
) -> Plan:
    terms = AcquisitionTerms(
        timing=_timing(decision, baseline.base_date),
        price=Decimal(decision.magnitude.value),
        target_revenue=Decimal(decision.target_revenue),
        target_ebitda_margin=Decimal(decision.target_ebitda_margin),
        deal_cost_fraction=Decimal(decision.deal_cost_fraction),
        integration_cost_fraction=central_value(decision.integration_cost_fraction),
        cost_synergy_fraction=central_value(decision.cost_synergy_fraction),
        new_debt_rate=Decimal(decision.new_debt_interest_rate),
        funding=_funding(decision.financing),
        ppe_share=accounting.acquired_ppe_share,
        intangibles_share=accounting.acquired_intangibles_share,
        intangibles_life_quarters=accounting.acquired_intangibles_life_years * QUARTERS_PER_YEAR,
        completed=completed,
    )
    return acquisition(baseline, terms)


def _divestiture(decision: Divestiture, baseline: Baseline) -> Plan:
    use = decision.use_of_proceeds
    terms = DivestitureTerms(
        timing=_timing(decision, baseline.base_date),
        revenue_fraction=Decimal(decision.magnitude.value),
        unit_ebitda_margin=Decimal(decision.segment_ebitda_margin),
        proceeds=Decimal(decision.disposal_proceeds),
        separation_cost_fraction=Decimal(decision.separation_cost_fraction),
        stranded_cost_fraction=central_value(decision.stranded_cost_fraction),
        tax_rate_on_gain=Decimal(decision.tax_rate_on_gain),
        debt_paydown=Decimal(use.debt_paydown),
        cash_retained=Decimal(use.cash_retained),
        shareholder_distribution=Decimal(use.shareholder_distribution),
    )
    return divestiture(baseline, terms)


def _capex(decision: CapexExpansion, baseline: Baseline) -> Plan:
    terms = CapexTerms(
        timing=_timing(decision, baseline.base_date),
        investment=Decimal(decision.magnitude.value),
        capacity_increase=Decimal(decision.capacity_increase),
        useful_life_years=decision.useful_life_years,
        utilization=central_value(decision.utilization),
        new_debt_rate=Decimal(decision.new_debt_interest_rate),
        funding=_funding(decision.financing),
    )
    return capex_expansion(baseline, terms)


def _refinance(decision: DebtRefinance, baseline: Baseline) -> Plan:
    """The form states the rate it replaces; the books hold one. They must agree."""
    tranches = baseline.opening.tranches
    principal = sum((tranche.principal for tranche in tranches), ZERO)
    weighted = sum((tranche.principal * tranche.annual_rate for tranche in tranches), ZERO)
    current = Decimal(decision.current_interest_rate)
    if not principal or abs(weighted / principal - current) > RATE_TOLERANCE:
        raise FinanceError(
            "current_rate_mismatch",
            "decision.current_interest_rate",
            f"{current} is not the rate of the debt on the books",
        )
    terms = RefinanceTerms(
        timing=_timing(decision, baseline.base_date),
        amount=Decimal(decision.magnitude.value),
        new_rate=central_value(decision.new_interest_rate),
        new_maturity_years=decision.new_maturity_years,
        fee_fraction=Decimal(decision.refinancing_fee_fraction),
    )
    return debt_refinance(baseline, terms)


@exact
def plan_for(
    decision: DecisionModel,
    baseline: Baseline,
    accounting: Accounting | None = None,
    completed: bool = True,
) -> Plan:
    """The plan of a contract decision at the central value of each uncertain parameter."""
    books = accounting if accounting is not None else Accounting()
    if isinstance(decision, RndChange):
        return _rnd(decision, baseline, books)
    if isinstance(decision, WorkforceRestructure):
        return _workforce(decision, baseline)
    if isinstance(decision, Acquisition):
        return _acquisition(decision, baseline, books, completed)
    if isinstance(decision, Divestiture):
        return _divestiture(decision, baseline)
    if isinstance(decision, CapexExpansion):
        return _capex(decision, baseline)
    return _refinance(decision, baseline)
