"""Event accounting of the six decisions, line by line, against the baseline of the same company."""

from decimal import Decimal

import pytest

from multiverse_finance.engine import project
from multiverse_finance.exact import FinanceError
from multiverse_finance.example import illustrative_baseline, illustrative_capital
from multiverse_finance.interventions import (
    NO_REVENUE_RETURN,
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
from multiverse_finance.statements import Period, StatementPath
from multiverse_finance.valuation import discount_factor, enterprise_value

D = Decimal
TINY = D("1e-20")
BASE = illustrative_baseline()
PATH = project(BASE)
GROWTH = D("0.025")


def book(plan: Plan) -> StatementPath:
    return project(BASE, [plan])


def at(path: StatementPath, quarter: int) -> Period:
    return path.periods[quarter - 1]


def close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) < TINY


def rnd(**terms: object) -> RndTerms:
    settings: dict[str, object] = {
        "timing": Timing(2, lag_quarters=1, ramp_quarters=2),
        "fraction_of_budget": D("0.5"),
    } | terms
    return RndTerms(**settings)  # type: ignore[arg-type]


def budget(quarter: int) -> Decimal:
    return at(PATH, quarter).income.rd_expense


def test_rnd_cost_starts_after_the_lag_and_ramps() -> None:
    path = book(rnd_change(BASE, rnd()))
    assert at(path, 2).income.rd_expense == budget(2)
    assert close(at(path, 3).income.rd_expense, budget(3) * D("1.25"))
    assert close(at(path, 4).income.rd_expense, budget(4) * D("1.5"))


def test_rnd_moves_ebit_and_ebitda_by_the_same_amount_now() -> None:
    path = book(rnd_change(BASE, rnd()))
    change = budget(4) * D("0.5")
    assert close(at(PATH, 4).income.ebitda - at(path, 4).income.ebitda, change)
    assert close(at(PATH, 4).income.ebit - at(path, 4).income.ebit, change)


def test_rnd_in_points_of_revenue_divides_by_a_hundred() -> None:
    plan = rnd_change(BASE, rnd(fraction_of_budget=None, points_of_revenue=D(2)))
    path = book(plan)
    assert close(at(path, 4).income.rd_expense - budget(4), D("0.02") * at(PATH, 4).income.revenue)


def test_rnd_needs_exactly_one_unit() -> None:
    with pytest.raises(FinanceError, match="magnitude"):
        rnd(points_of_revenue=D(2))


def test_rnd_without_a_measured_return_adds_no_revenue_and_says_so() -> None:
    plan = rnd_change(BASE, rnd())
    assert NO_REVENUE_RETURN in plan.notes
    assert book(plan).periods[-1].income.revenue == PATH.periods[-1].income.revenue


def test_rnd_revenue_arrives_only_after_the_adoption_delay() -> None:
    terms = rnd(adoption_delay_quarters=4, revenue_return=D(2))
    path = book(rnd_change(BASE, terms))
    assert at(path, 6).income.revenue == at(PATH, 6).income.revenue
    assert close(at(path, 7).income.revenue - at(PATH, 7).income.revenue, budget(3) * D("0.25") * 2)


def test_capitalizing_rnd_moves_cost_from_ebitda_to_amortization_not_cash() -> None:
    expensed = book(rnd_change(BASE, rnd()))
    capitalized = book(rnd_change(BASE, rnd(capitalized_fraction=D("0.5"))))
    assert at(capitalized, 4).income.ebitda > at(expensed, 4).income.ebitda
    assert at(capitalized, 4).income.amortization > at(expensed, 4).income.amortization
    assert at(capitalized, 4).balance.intangibles > at(expensed, 4).balance.intangibles
    for path_quarter in (2, 3, 4, 5):
        one, two = at(capitalized, path_quarter), at(expensed, path_quarter)
        assert close(
            one.free_cash.fcff + one.free_cash.tax_on_ebit,
            two.free_cash.fcff + two.free_cash.tax_on_ebit,
        )


def test_a_cut_of_rnd_needs_no_funding_and_capitalizes_nothing() -> None:
    plan = rnd_change(BASE, rnd(fraction_of_budget=D("-0.3"), capitalized_fraction=D("0.5")))
    assert plan.funding == ()
    assert book(plan).periods[-1].balance.intangibles == PATH.periods[-1].balance.intangibles


def test_rnd_can_be_funded_with_debt_at_the_marginal_rate() -> None:
    plan = rnd_change(BASE, rnd(funding=Funding(D(0), D(1), D(0))))
    path = book(plan)
    assert at(path, 3).cash_flow.debt_drawn == budget(3) * D("0.25")
    assert at(path, 3).balance.term_debt > at(PATH, 3).balance.term_debt


def layoff(**terms: object) -> WorkforceTerms:
    settings: dict[str, object] = {
        "timing": Timing(2, lag_quarters=1, ramp_quarters=2),
        "headcount_change": D("-0.15"),
        "payroll_to_revenue": D("0.30"),
        "one_off_cost_months": D(6),
        "savings_realization": D("0.8"),
    } | terms
    return WorkforceTerms(**settings)  # type: ignore[arg-type]


def costs(period: Period) -> Decimal:
    return period.income.cogs + period.income.rd_expense + period.income.sga


def test_savings_are_partial_and_ramp() -> None:
    path = book(workforce_restructure(BASE, layoff()))
    revenue = at(PATH, 6).income.revenue
    saved = costs(at(PATH, 6)) - costs(at(path, 6))
    assert close(saved, D("0.15") * D("0.30") * revenue * D("0.8"))
    assert saved < D("0.15") * costs(at(PATH, 6))
    half = costs(at(PATH, 3)) - costs(at(path, 3))
    assert close(half, D("0.15") * D("0.30") * at(PATH, 3).income.revenue * D("0.8") / 2)


def test_severance_is_charged_at_commitment_and_paid_when_people_leave() -> None:
    path = book(workforce_restructure(BASE, layoff()))
    charge = D("0.15") * D("0.30") * at(PATH, 2).income.revenue * 4 * D(6) / 12
    assert close(at(path, 2).income.one_off, charge)
    assert close(at(path, 2).balance.provision, charge)
    assert close(at(path, 3).balance.provision, charge / 2)
    assert close(at(path, 4).balance.provision, D(0))


def test_adjusted_ebitda_adds_back_only_the_one_off() -> None:
    path = book(workforce_restructure(BASE, layoff()))
    period = at(path, 2)
    assert period.income.adjusted_ebitda == period.income.ebitda + period.income.one_off
    assert period.income.adjusted_ebitda == at(PATH, 2).income.adjusted_ebitda


def test_productivity_loss_lowers_revenue_during_the_ramp_only() -> None:
    path = book(workforce_restructure(BASE, layoff(productivity_loss=D("0.1"))))
    assert close(
        at(PATH, 3).income.revenue - at(path, 3).income.revenue,
        D("0.1") * D("0.5") * at(PATH, 3).income.revenue,
    )
    assert at(path, 4).income.revenue == at(PATH, 4).income.revenue


def test_hiring_costs_are_expensed_as_paid_with_no_provision() -> None:
    path = book(workforce_restructure(BASE, layoff(headcount_change=D("0.10"))))
    assert all(period.balance.provision == 0 for period in path.periods)
    assert at(path, 3).income.one_off > 0
    assert costs(at(path, 6)) > costs(at(PATH, 6))


def test_payroll_above_all_costs_is_impossible() -> None:
    with pytest.raises(FinanceError, match="payroll_exceeds_costs"):
        workforce_restructure(BASE, layoff(payroll_to_revenue=D("0.9")))


def deal(**terms: object) -> AcquisitionTerms:
    settings: dict[str, object] = {
        "timing": Timing(2, lag_quarters=1, ramp_quarters=4),
        "price": D(1200),
        "target_revenue": D(800),
        "target_ebitda_margin": D("0.2"),
        "deal_cost_fraction": D("0.02"),
        "integration_cost_fraction": D("0.05"),
        "cost_synergy_fraction": D("0.03"),
        "new_debt_rate": D("0.07"),
        "funding": Funding(D("0.3"), D("0.5"), D("0.2")),
        "ppe_share": D("0.15"),
        "intangibles_share": D("0.25"),
        "intangibles_life_quarters": 40,
    } | terms
    return AcquisitionTerms(**settings)  # type: ignore[arg-type]


def test_sources_equal_uses_with_cash_debt_and_equity() -> None:
    plan = acquisition(BASE, deal())
    (table,) = plan.funding
    assert dict(table.sources) == {
        "cash on hand": D("0.3") * 1224,
        "new debt": D("0.5") * 1224,
        "new equity": D("0.2") * 1224,
    }
    assert dict(table.uses) == {"purchase price": D(1200), "deal costs": D(24)}
    assert table.residual == 0


def test_funding_shares_must_add_up_to_exactly_one() -> None:
    with pytest.raises(FinanceError, match="shares_sum"):
        Funding(D("0.5"), D("0.4"), D(0))


def test_new_debt_needs_a_rate() -> None:
    with pytest.raises(FinanceError, match="rate_required"):
        deal(new_debt_rate=D(0))


def test_closing_books_goodwill_as_the_rest_of_the_price() -> None:
    path = book(acquisition(BASE, deal()))
    nwc = D("0.10") * 800
    goodwill = D(1200) - D("0.15") * 1200 - D("0.25") * 1200 - nwc
    assert at(path, 2).balance.goodwill == at(PATH, 2).balance.goodwill
    assert at(path, 3).balance.goodwill == at(PATH, 3).balance.goodwill + goodwill
    assert at(path, 3).cash_flow.acquisitions == 1200


def test_identified_assets_above_the_price_are_refused() -> None:
    with pytest.raises(FinanceError, match="negative_goodwill"):
        book(acquisition(BASE, deal(ppe_share=D("0.6"), intangibles_share=D("0.5"))))


def test_target_results_join_from_closing_with_its_own_margin() -> None:
    path = book(acquisition(BASE, deal(cost_synergy_fraction=D(0), integration_cost_fraction=D(0))))
    period = at(path, 4)
    assert dict(period.income.segments)["acquired"] == 200
    assert close(period.income.ebitda - at(PATH, 4).income.ebitda, D(40))
    assert "acquired" not in dict(at(path, 2).income.segments)


def test_interest_on_new_debt_starts_at_closing() -> None:
    path = book(acquisition(BASE, deal()))
    extra = at(path, 3).income.interest_expense - at(PATH, 3).income.interest_expense
    assert close(extra, D("0.5") * 1224 * D("0.07") / 4)


def test_integration_is_spread_over_the_ramp_and_synergies_wait_for_its_end() -> None:
    path = book(acquisition(BASE, deal()))
    assert close(at(path, 4).income.one_off, D("0.05") * 1200 / 4)
    before = at(path, 6).income.ebitda - at(PATH, 6).income.ebitda
    after = at(path, 7).income.ebitda - at(PATH, 7).income.ebitda
    assert close(before, D(40) - D(15))
    assert close(after, D(40) + D("0.03") * 200)


def test_delayed_synergies_arrive_later() -> None:
    path = book(acquisition(BASE, deal(synergy_delay_quarters=2)))
    assert close(at(path, 8).income.ebitda - at(PATH, 8).income.ebitda, D(40))
    assert close(at(path, 9).income.ebitda - at(PATH, 9).income.ebitda, D(46))


def test_a_failed_deal_costs_its_deal_costs_and_nothing_else() -> None:
    plan = acquisition(BASE, deal(completed=False))
    path = book(plan)
    assert at(path, 3).income.one_off == 24
    assert at(path, 3).cash_flow.acquisitions == 0
    assert at(path, 3).cash_flow.debt_drawn == 0
    assert at(path, 3).balance.goodwill == at(PATH, 3).balance.goodwill
    assert at(path, 3).income.revenue == at(PATH, 3).income.revenue
    assert plan.funding[0].residual == 0


def test_paying_the_price_does_not_add_the_price_to_value() -> None:
    capital = illustrative_capital()
    base = enterprise_value(PATH, capital, GROWTH).enterprise_value
    empty = deal(
        target_revenue=D(0),
        deal_cost_fraction=D(0),
        integration_cost_fraction=D(0),
        ppe_share=D(0),
        intangibles_share=D(0),
    )
    bought = enterprise_value(book(acquisition(BASE, empty)), capital, GROWTH).enterprise_value
    assert base is not None
    assert bought is not None
    assert close(bought - base, -1200 * discount_factor(3, capital.wacc))


def test_how_a_deal_is_funded_does_not_change_fcff() -> None:
    cash = book(acquisition(BASE, deal(funding=Funding(D(1), D(0), D(0)))))
    debt = book(acquisition(BASE, deal(funding=Funding(D(0), D(1), D(0)))))
    equity = book(acquisition(BASE, deal(funding=Funding(D(0), D(0), D(1)))))
    for one, two, three in zip(cash.periods, debt.periods, equity.periods, strict=True):
        assert close(one.free_cash.fcff, two.free_cash.fcff)
        assert close(two.free_cash.fcff, three.free_cash.fcff)
    assert at(debt, 5).free_cash.fcfe != at(equity, 5).free_cash.fcfe


def sale(**terms: object) -> DivestitureTerms:
    settings: dict[str, object] = {
        "timing": Timing(2, lag_quarters=1, ramp_quarters=2),
        "revenue_fraction": D("0.2"),
        "unit_ebitda_margin": D("0.1"),
        "proceeds": D(1000),
        "separation_cost_fraction": D("0.01"),
        "stranded_cost_fraction": D("0.4"),
        "tax_rate_on_gain": D("0.25"),
        "debt_paydown": D("0.5"),
        "cash_retained": D("0.3"),
        "shareholder_distribution": D("0.2"),
    } | terms
    return DivestitureTerms(**settings)  # type: ignore[arg-type]


def test_revenue_of_the_unit_leaves_at_closing_from_every_segment() -> None:
    path = book(divestiture(BASE, sale()))
    assert at(path, 2).income.revenue == at(PATH, 2).income.revenue
    assert close(at(path, 3).income.revenue, at(PATH, 3).income.revenue * D("0.8"))


def test_ebitda_falls_by_the_unit_plus_stranded_overhead() -> None:
    path = book(divestiture(BASE, sale()))
    revenue = at(PATH, 6).income.revenue
    unit = D("0.2") * revenue
    overhead = unit * D("0.17")
    lost = at(PATH, 6).income.ebitda - at(path, 6).income.ebitda
    assert close(lost, unit * D("0.1") + overhead * D("0.4"))


def test_stranded_overhead_starts_whole_and_settles_over_the_ramp() -> None:
    path = book(divestiture(BASE, sale(separation_cost_fraction=D(0))))
    revenue = at(PATH, 3).income.revenue
    unit = D("0.2") * revenue
    lost = at(PATH, 3).income.ebitda - at(path, 3).income.ebitda
    assert close(lost, unit * D("0.1") + unit * D("0.17") * D("0.7"))


def test_a_loss_making_unit_raises_ebitda_when_it_leaves() -> None:
    path = book(divestiture(BASE, sale(unit_ebitda_margin=D("-0.3"), stranded_cost_fraction=D(0))))
    assert at(path, 6).income.ebitda > at(PATH, 6).income.ebitda


def test_gain_is_proceeds_over_book_value_and_only_a_gain_is_taxed() -> None:
    path = book(divestiture(BASE, sale()))
    before = at(PATH, 2).balance
    book_value = D("0.2") * (before.trade_nwc + before.ppe + before.intangibles + before.goodwill)
    assert close(at(path, 3).income.disposal_gain, 1000 - book_value)
    assert close(at(path, 3).income.disposal_tax, (1000 - book_value) * D("0.25"))
    low = book(divestiture(BASE, sale(proceeds=D(100))))
    assert at(low, 3).income.disposal_gain < 0
    assert at(low, 3).income.disposal_tax == 0


def test_book_assets_of_the_unit_leave_and_the_gain_is_not_operating_cash() -> None:
    path = book(divestiture(BASE, sale()))
    period = at(path, 3)
    assert period.balance.goodwill == at(PATH, 3).balance.goodwill * D("0.8")
    assert period.cash_flow.disposal_proceeds == 1000
    assert period.income.disposal_gain != 0
    assert period.free_cash.transactions == 1000 - period.income.disposal_tax


def test_net_proceeds_go_where_the_decision_says() -> None:
    path = book(divestiture(BASE, sale()))
    (table,) = path.funding
    uses = dict(table.uses)
    net = D(1000) - uses["separation cost"] - uses["tax on the gain"]
    assert close(uses["debt paid down"], net * D("0.5"))
    assert close(uses["distribution to shareholders"], net * D("0.2"))
    assert close(uses["cash retained"], net * D("0.3"))
    assert close(table.residual, D(0))


def test_paydown_above_the_debt_stays_in_cash() -> None:
    plan = divestiture(
        BASE,
        sale(
            proceeds=D(10000), debt_paydown=D(1), cash_retained=D(0), shareholder_distribution=D(0)
        ),
    )
    path = book(plan)
    (table,) = path.funding
    assert close(dict(table.uses)["debt paid down"], at(PATH, 3).balance.term_debt)
    assert dict(table.uses)["cash retained"] > 0
    assert close(table.residual, D(0))


def test_closing_a_unit_for_nothing_is_paid_from_cash() -> None:
    path = book(divestiture(BASE, sale(proceeds=D(0))))
    (table,) = path.funding
    assert dict(table.sources)["cash on hand"] > 0
    assert at(path, 3).income.disposal_gain < 0
    assert close(table.residual, D(0))


def test_proceeds_shares_must_add_up() -> None:
    with pytest.raises(FinanceError, match="shares_sum"):
        sale(debt_paydown=D("0.6"))


def plant(**terms: object) -> CapexTerms:
    settings: dict[str, object] = {
        "timing": Timing(2, lag_quarters=2, ramp_quarters=4),
        "investment": D(800),
        "capacity_increase": D("0.3"),
        "useful_life_years": 10,
        "utilization": D("0.75"),
        "new_debt_rate": D("0.07"),
        "funding": Funding(D("0.5"), D("0.5"), D(0)),
    } | terms
    return CapexTerms(**settings)  # type: ignore[arg-type]


def test_cash_leaves_during_construction_before_any_revenue() -> None:
    path = book(capex_expansion(BASE, plant()))
    assert close(at(path, 2).cash_flow.capex - at(PATH, 2).cash_flow.capex, D(400))
    assert close(at(path, 3).cash_flow.capex - at(PATH, 3).cash_flow.capex, D(400))
    assert at(path, 3).income.revenue == at(PATH, 3).income.revenue
    assert at(path, 3).free_cash.fcff < at(PATH, 3).free_cash.fcff


def test_depreciation_starts_when_the_asset_is_in_use() -> None:
    path = book(capex_expansion(BASE, plant()))
    assert at(path, 3).income.depreciation == at(PATH, 3).income.depreciation
    extra = at(path, 4).income.depreciation - at(PATH, 4).income.depreciation
    assert close(extra, D(800) / 40)


def test_revenue_follows_utilization_and_the_ramp_not_capacity() -> None:
    path = book(capex_expansion(BASE, plant()))
    revenue = at(PATH, 7).income.revenue
    extra = at(path, 7).income.revenue - revenue
    assert close(extra, revenue * D("0.3") * D("0.75"))
    assert extra < revenue * D("0.3")
    first = at(path, 4).income.revenue - at(PATH, 4).income.revenue
    assert close(first, at(PATH, 4).income.revenue * D("0.3") * D("0.75") / 4)


def test_idle_capacity_still_depreciates_and_earns_nothing() -> None:
    path = book(capex_expansion(BASE, plant(utilization=D(0))))
    assert at(path, 8).income.revenue == at(PATH, 8).income.revenue
    assert close(at(path, 8).income.depreciation - at(PATH, 8).income.depreciation, D(20))


def test_a_sale_during_construction_takes_its_share_of_the_unfinished_asset() -> None:
    build = capex_expansion(BASE, plant(timing=Timing(1, lag_quarters=4), capacity_increase=D(0)))
    leave = divestiture(BASE, sale(timing=Timing(3), revenue_fraction=D("0.25")))
    path = project(BASE, [build, leave])
    alone = project(BASE, [leave])
    extra = at(path, 5).income.depreciation - at(alone, 5).income.depreciation
    assert close(extra, D(700) / 40)


def test_capex_funding_table() -> None:
    (table,) = capex_expansion(BASE, plant()).funding
    assert table.residual == 0
    assert dict(table.sources)["new debt"] == 400


def test_construction_that_outlasts_the_horizon_funds_only_what_is_spent() -> None:
    late = plant(timing=Timing(11, lag_quarters=4))
    plan = capex_expansion(BASE, late)
    (table,) = plan.funding
    assert dict(table.uses)["investment"] == 400
    assert book(plan).periods[-1].income.depreciation == PATH.periods[-1].income.depreciation


def refinance(**terms: object) -> RefinanceTerms:
    settings: dict[str, object] = {
        "timing": Timing(2, lag_quarters=1),
        "amount": D(500),
        "new_rate": D("0.04"),
        "new_maturity_years": 5,
        "fee_fraction": D("0.01"),
    } | terms
    return RefinanceTerms(**settings)  # type: ignore[arg-type]


def test_refinancing_keeps_the_debt_and_changes_the_interest() -> None:
    path = book(debt_refinance(BASE, refinance()))
    assert at(path, 3).balance.term_debt == at(PATH, 3).balance.term_debt
    saved = at(PATH, 3).income.interest_expense - at(path, 3).income.interest_expense
    assert close(saved, D(500) * (D("0.05") - D("0.04")) / 4)


def test_refinancing_fee_is_expensed_paid_and_stays_out_of_ebitda_and_fcff() -> None:
    path = book(debt_refinance(BASE, refinance()))
    assert at(path, 3).income.financing_fees == 5
    assert at(path, 3).income.ebitda == at(PATH, 3).income.ebitda
    assert at(path, 3).free_cash.fcff == at(PATH, 3).free_cash.fcff
    assert at(path, 3).free_cash.fcfe < at(PATH, 3).free_cash.fcfe


def test_refinancing_table_and_the_new_maturity_beyond_the_old_one() -> None:
    plan = debt_refinance(BASE, refinance())
    assert plan.funding[0].residual == 0
    path = book(plan)
    assert at(path, 8).cash_flow.debt_repaid == 500
    assert at(path, 8).cash_flow.debt_drawn == 500


def test_refinancing_over_a_ramp_replaces_part_by_part() -> None:
    path = book(debt_refinance(BASE, refinance(timing=Timing(2, ramp_quarters=2))))
    assert at(path, 2).cash_flow.debt_drawn == 250
    assert at(path, 3).cash_flow.debt_drawn == 250


def test_refinancing_more_than_the_debt_is_impossible() -> None:
    with pytest.raises(FinanceError, match="impossible_debt"):
        debt_refinance(BASE, refinance(amount=D(1501)))


def test_refinancing_debt_already_repaid_is_impossible_on_the_path() -> None:
    late = refinance(timing=Timing(9), amount=D(1500))
    closed = illustrative_baseline()
    from dataclasses import replace

    shut = replace(closed, policy=replace(closed.policy, can_refinance=False))
    with pytest.raises(FinanceError, match="impossible_debt"):
        project(shut, [debt_refinance(shut, late)])


ZERO_PLANS = [
    rnd_change(BASE, rnd(fraction_of_budget=D(0))),
    workforce_restructure(BASE, layoff(headcount_change=D(0))),
    acquisition(
        BASE,
        deal(
            price=D(0),
            target_revenue=D(0),
            target_ebitda_margin=D(0),
            ppe_share=D(0),
            intangibles_share=D(0),
            cost_synergy_fraction=D(0),
        ),
    ),
    acquisition(BASE, deal(price=D(0), completed=False)),
    divestiture(BASE, sale(revenue_fraction=D(0), proceeds=D(0))),
    capex_expansion(BASE, plant(investment=D(0), capacity_increase=D(0))),
    debt_refinance(BASE, refinance(amount=D(0))),
]


@pytest.mark.parametrize("plan", ZERO_PLANS, ids=lambda plan: plan.decision)
def test_a_decision_of_size_zero_is_the_baseline_exactly(plan: Plan) -> None:
    assert book(plan).periods == PATH.periods


def test_decisions_add_up_on_one_path_and_still_reconcile() -> None:
    plans = [
        rnd_change(BASE, rnd()),
        workforce_restructure(BASE, layoff()),
        acquisition(BASE, deal()),
        divestiture(BASE, sale()),
        capex_expansion(BASE, plant()),
        debt_refinance(BASE, refinance()),
    ]
    assert len(project(BASE, plans).periods) == BASE.horizon
