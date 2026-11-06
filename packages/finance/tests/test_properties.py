"""Properties that must hold on any company and any decision, not on chosen examples.

``project`` itself refuses a path that does not reconcile, so a run that returns has passed every
identity. Only settings that are impossible by definition may be refused here: never
``reconciliation``.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from multiverse_finance.checks import TOLERANCE, residuals
from multiverse_finance.engine import project
from multiverse_finance.exact import FinanceError
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
from multiverse_finance.model import Baseline, Drivers, Opening, Policy, Tranche
from multiverse_finance.valuation import discounted

D = Decimal
HORIZON = 10
IMPOSSIBLE = {"negative_line", "impossible_debt", "negative_goodwill", "payroll_exceeds_costs"}


def amounts(low: int, high: int) -> st.SearchStrategy[Decimal]:
    return st.decimals(low, high, places=2, allow_nan=False, allow_infinity=False)


def fractions(low: str = "0", high: str = "1") -> st.SearchStrategy[Decimal]:
    return st.decimals(D(low), D(high), places=3, allow_nan=False, allow_infinity=False)


@st.composite
def fundings(draw: st.DrawFn) -> Funding:
    cash = draw(fractions())
    debt = draw(fractions("0", "1").filter(lambda share: share <= 1 - cash))
    return Funding(cash, debt, 1 - cash - debt)


@st.composite
def timings(draw: st.DrawFn) -> Timing:
    return Timing(draw(st.integers(1, 12)), draw(st.integers(0, 6)), draw(st.integers(0, 6)))


@st.composite
def baselines(draw: st.DrawFn) -> Baseline:
    first = draw(amounts(10, 5000))
    growth = draw(fractions("-0.1", "0.1"))
    cogs = draw(fractions("0.1", "0.9"))
    quarters = tuple(
        Drivers(
            segments=(("a", first * (1 + growth) ** n), ("b", first / 2)),
            cogs_ratio=cogs,
            rd_ratio=draw(fractions("0", "0.2")),
            sga_ratio=draw(fractions("0", "0.4")),
            capex_ratio=draw(fractions("0", "0.2")),
            nwc_ratio=draw(fractions("-0.2", "0.4")),
        )
        for n in range(HORIZON)
    )
    principal = draw(amounts(0, 5000))
    opening = Opening(
        cash=draw(amounts(0, 2000)),
        trade_nwc=draw(amounts(-200, 800)),
        ppe=draw(amounts(0, 4000)),
        intangibles=draw(amounts(0, 500)),
        goodwill=draw(amounts(0, 500)),
        non_operating_assets=draw(amounts(0, 200)),
        tranches=(
            Tranche(
                "a",
                principal,
                draw(fractions("0", "0.15")),
                maturity_quarter=draw(st.none() | st.integers(1, HORIZON)),
            ),
        ),
        tax_losses=draw(amounts(0, 300)),
    )
    policy = Policy(
        tax_rate=draw(fractions("0", "0.5")),
        depreciation_rate=draw(fractions("0", "0.3")),
        amortization_rate=draw(fractions("0", "0.3")),
        cash_yield=draw(fractions("0", "0.05")),
        minimum_cash=draw(amounts(0, 300)),
        revolver_limit=draw(amounts(0, 800)),
        revolver_rate=draw(fractions("0", "0.2")),
        marginal_debt_rate=draw(fractions("0", "0.2")),
        can_refinance=draw(st.booleans()),
        dividend_payout=draw(fractions()),
    )
    return Baseline("USD", date(2026, 6, 30), opening, policy, quarters)


@st.composite
def plans(draw: st.DrawFn, baseline: Baseline) -> Plan:
    timing = draw(timings())
    funding = draw(fundings())
    rate = draw(fractions("0.01", "0.2"))
    kind = draw(st.integers(0, 5))
    if kind == 0:
        return rnd_change(
            baseline,
            RndTerms(
                timing=timing,
                fraction_of_budget=draw(fractions("-0.9", "3")),
                capitalized_fraction=draw(fractions()),
                adoption_delay_quarters=draw(st.integers(0, 12)),
                revenue_return=draw(fractions("0", "2")),
                funding=funding,
            ),
        )
    if kind == 1:
        return workforce_restructure(
            baseline,
            WorkforceTerms(
                timing=timing,
                headcount_change=draw(fractions("-0.6", "0.5")),
                payroll_to_revenue=draw(fractions("0.01", "0.5")),
                one_off_cost_months=draw(fractions("0", "24")),
                savings_realization=draw(fractions()),
                productivity_loss=draw(fractions("0", "0.5")),
                funding=funding,
            ),
        )
    if kind == 2:
        return acquisition(
            baseline,
            AcquisitionTerms(
                timing=timing,
                price=draw(amounts(0, 6000)),
                target_revenue=draw(amounts(0, 4000)),
                target_ebitda_margin=draw(fractions("-1", "0.8")),
                deal_cost_fraction=draw(fractions("0", "0.1")),
                integration_cost_fraction=draw(fractions("0", "0.3")),
                cost_synergy_fraction=draw(fractions("0", "0.3")),
                new_debt_rate=rate,
                funding=funding,
                ppe_share=draw(fractions("0", "0.4")),
                intangibles_share=draw(fractions("0", "0.4")),
                completed=draw(st.booleans()),
                synergy_delay_quarters=draw(st.integers(0, 6)),
            ),
        )
    if kind == 3:
        paydown = draw(fractions())
        kept = draw(fractions().filter(lambda share: share <= 1 - paydown))
        return divestiture(
            baseline,
            DivestitureTerms(
                timing=timing,
                revenue_fraction=draw(fractions("0.01", "0.9")),
                unit_ebitda_margin=draw(fractions("-1", "0.8")),
                proceeds=draw(amounts(0, 8000)),
                separation_cost_fraction=draw(fractions("0", "0.5")),
                stranded_cost_fraction=draw(fractions()),
                tax_rate_on_gain=draw(fractions("0", "0.5")),
                debt_paydown=paydown,
                cash_retained=kept,
                shareholder_distribution=1 - paydown - kept,
            ),
        )
    if kind == 4:
        return capex_expansion(
            baseline,
            CapexTerms(
                timing=timing,
                investment=draw(amounts(0, 5000)),
                capacity_increase=draw(fractions("0.01", "2")),
                useful_life_years=draw(st.integers(3, 50)),
                utilization=draw(fractions()),
                new_debt_rate=rate,
                funding=funding,
            ),
        )
    return debt_refinance(
        baseline,
        RefinanceTerms(
            timing=timing,
            amount=draw(amounts(0, 5000)),
            new_rate=draw(fractions("0", "0.3")),
            new_maturity_years=draw(st.integers(1, 40)),
            fee_fraction=draw(fractions("0", "0.05")),
        ),
    )


@st.composite
def cases(draw: st.DrawFn) -> tuple[Baseline, tuple[Plan, ...]]:
    baseline = draw(baselines())
    count = draw(st.integers(1, 3))
    try:
        chosen = tuple(draw(plans(baseline)) for _ in range(count))
    except FinanceError as error:
        assume(error.code in IMPOSSIBLE and False)
        raise
    return baseline, chosen


def run(baseline: Baseline, chosen: tuple[Plan, ...]):  # type: ignore[no-untyped-def]
    try:
        return project(baseline, chosen)
    except FinanceError as error:
        assert error.code in IMPOSSIBLE, error  # noqa: PT017
        assume(False)
        raise


@settings(max_examples=300)
@given(cases())
def test_every_path_reconciles_and_stays_inside_its_limits(
    case: tuple[Baseline, tuple[Plan, ...]],
) -> None:
    baseline, chosen = case
    path = run(baseline, chosen)
    assert all(abs(item.value) <= TOLERANCE for item in residuals(path, baseline))
    limit = baseline.policy.revolver_limit
    for period in path.periods:
        balance = period.balance
        assert balance.cash >= 0
        assert balance.shortfall >= 0
        assert 0 <= balance.revolver <= limit
        assert balance.term_debt >= -TOLERANCE
        assert period.tax_losses >= 0
        assert period.income.ordinary_tax >= 0
        assert period.income.disposal_tax >= 0
        assert period.cash_flow.dividends >= 0
        leverage = period.credit.leverage
        assert (leverage.value is None) == (leverage.reason is not None)


@settings(max_examples=200)
@given(cases())
def test_sources_equal_uses_in_every_funding_table(
    case: tuple[Baseline, tuple[Plan, ...]],
) -> None:
    baseline, chosen = case
    path = run(baseline, chosen)
    assert all(abs(table.residual) <= TOLERANCE for table in path.funding)


@settings(max_examples=100)
@given(cases())
def test_the_same_case_gives_the_same_path(case: tuple[Baseline, tuple[Plan, ...]]) -> None:
    baseline, chosen = case
    assert run(baseline, chosen) == run(baseline, chosen)


@settings(max_examples=150)
@given(baselines())
def test_no_decision_means_an_empty_plan_changes_nothing(baseline: Baseline) -> None:
    assert project(baseline, [Plan("nothing", ())]).periods == project(baseline).periods


@settings(max_examples=150)
@given(baselines(), timings(), fundings())
def test_zero_effect_identity_on_any_company_and_timing(
    baseline: Baseline, timing: Timing, funding: Funding
) -> None:
    zero = D(0)
    plan_set = [
        rnd_change(baseline, RndTerms(timing, fraction_of_budget=zero, funding=funding)),
        workforce_restructure(baseline, WorkforceTerms(timing, zero, zero, zero, zero, zero)),
        capex_expansion(baseline, CapexTerms(timing, zero, zero, 5, zero, D("0.05"), funding)),
        debt_refinance(baseline, RefinanceTerms(timing, zero, zero, 1, zero)),
        divestiture(
            baseline,
            DivestitureTerms(timing, zero, zero, zero, zero, zero, zero, D(1), zero, zero),
        ),
        acquisition(
            baseline,
            AcquisitionTerms(timing, zero, zero, zero, zero, zero, zero, D("0.05"), funding),
        ),
    ]
    expected = project(baseline).periods
    for plan in plan_set:
        assert project(baseline, [plan]).periods == expected


@settings(max_examples=200)
@given(baselines())
def test_when_lenders_are_shut_rolling_is_not_possible(baseline: Baseline) -> None:
    shut = replace(baseline, policy=replace(baseline.policy, can_refinance=False))
    for period in project(shut).periods:
        assert period.cash_flow.debt_drawn == 0


@given(
    st.lists(amounts(-500, 500), min_size=4, max_size=40),
    st.lists(amounts(1, 500), min_size=4, max_size=4),
    fractions("0.01", "0.25"),
    fractions("-0.05", "0.05"),
)
def test_a_dcf_with_wacc_above_growth_is_finite(
    flows: list[Decimal], last_year: list[Decimal], rate: Decimal, growth: Decimal
) -> None:
    assume(rate > growth)
    dcf = discounted(flows, last_year, rate, growth)
    assert dcf.present_value.is_finite()
    assert dcf.enterprise_value is not None
    assert dcf.enterprise_value.is_finite()
    assert dcf.terminal_value is not None
    assert dcf.terminal_value > 0


@given(fractions("0.01", "0.25"), fractions("0", "0.3"))
def test_a_dcf_with_wacc_at_or_below_growth_never_returns(rate: Decimal, extra: Decimal) -> None:
    try:
        discounted([D(1)] * 4, [D(1)] * 4, rate, rate + extra)
    except FinanceError as error:
        assert error.code == "wacc_not_above_growth"  # noqa: PT017
    else:
        raise AssertionError("WACC <= g must be refused")


@given(amounts(1, 1000), fractions("0.02", "0.25"), fractions("0", "0.01"))
def test_value_falls_when_the_discount_rate_rises(
    flow: Decimal, rate: Decimal, growth: Decimal
) -> None:
    low = discounted([flow] * 4, [flow] * 4, rate, growth)
    high = discounted([flow] * 4, [flow] * 4, rate + D("0.01"), growth)
    assert low.enterprise_value is not None
    assert high.enterprise_value is not None
    assert high.enterprise_value < low.enterprise_value
