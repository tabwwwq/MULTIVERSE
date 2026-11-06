"""The statements on cases small enough to check by hand."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from multiverse_finance.checks import assert_reconciled, residuals
from multiverse_finance.engine import NO_EBITDA, NO_HISTORY, project
from multiverse_finance.exact import FinanceError
from multiverse_finance.example import illustrative_baseline
from multiverse_finance.ledger import Borrow, Charge, Flow, Line, Payment, Plan, SourcesUses
from multiverse_finance.model import Baseline, Drivers, Opening, Policy, Tranche
from multiverse_finance.statements import StatementPath

D = Decimal


def drivers(revenue: str = "100", cogs: str = "0.5", nwc: str = "0.1") -> Drivers:
    return Drivers(
        segments=(("all", D(revenue)),),
        cogs_ratio=D(cogs),
        rd_ratio=D("0.1"),
        sga_ratio=D("0.1"),
        capex_ratio=D("0.1"),
        nwc_ratio=D(nwc),
    )


def company(
    quarters: tuple[Drivers, ...] = (),
    cash: str = "100",
    tranches: tuple[Tranche, ...] = (Tranche("loan", D(200), D("0.08")),),
    **policy: object,
) -> Baseline:
    """Flat by construction: capex equals depreciation and NWC stays at 40."""
    opening = Opening(D(cash), D(40), D(400), D(0), D(0), D(0), tranches)
    settings: dict[str, object] = {
        "tax_rate": D("0.25"),
        "depreciation_rate": D("0.10"),
        "amortization_rate": D(0),
        "cash_yield": D(0),
        "minimum_cash": D(0),
        "revolver_limit": D(0),
        "revolver_rate": D("0.10"),
        "marginal_debt_rate": D("0.09"),
    } | policy
    return Baseline(
        "USD",
        date(2026, 6, 30),
        opening,
        Policy(**settings),  # type: ignore[arg-type]
        quarters or (drivers(),) * 4,
    )


def test_one_quarter_by_hand() -> None:
    first = project(company()).periods[0]
    income, cash, balance, free = first.income, first.cash_flow, first.balance, first.free_cash
    assert income.gross_profit == 50
    assert income.ebitda == 30
    assert income.depreciation == 10
    assert income.ebit == 20
    assert income.interest_expense == 4
    assert income.ordinary_tax == 4
    assert income.net_income == 12
    assert cash.cfo == 22
    assert cash.capex == 10
    assert balance.cash == 112
    assert balance.ppe == 400
    assert free.fcf_simple == 12
    assert free.fcff == 15
    assert free.fcfe == 12


def test_fcff_fcfe_and_cfo_minus_capex_are_three_different_things() -> None:
    plan = Plan("loan", (Flow(1, Line.ONE_OFF, D(0)),))
    free = project(company(), [plan]).periods[0].free_cash
    assert free.fcff != free.fcf_simple
    assert free.fcff - D(4) * (1 - D("0.25")) == free.fcfe


def test_interest_tax_shield_is_the_rate_on_interest_when_profit_covers_it() -> None:
    free = project(company()).periods[0].free_cash
    assert free.tax_shield == D(4) * D("0.25")


def test_nwc_growth_costs_cash_and_its_sign_is_checked() -> None:
    path = project(company((drivers("110"), drivers("110"), drivers("110"), drivers("110"))))
    first = path.periods[0]
    assert first.balance.trade_nwc == 44
    assert first.cash_flow.delta_nwc == 4
    assert first.free_cash.fcff < 15 * D("1.1")


def test_a_loss_earns_no_refund_and_is_used_later() -> None:
    bad, good = drivers(cogs="1"), drivers()
    path = project(company((bad, good, good, good), tranches=()))
    assert path.periods[0].income.ordinary_tax == 0
    assert path.periods[0].tax_losses == 30
    assert path.periods[1].income.pre_tax_income == 20
    assert path.periods[1].income.ordinary_tax == 0
    assert path.periods[1].tax_losses == 10
    assert path.periods[2].income.ordinary_tax == D(10) * D("0.25")
    assert path.periods[2].tax_losses == 0


def test_tax_on_ebit_keeps_its_own_losses() -> None:
    """With debt, the levered losses run ahead of the unlevered ones: both are tracked."""
    bad, good = drivers(cogs="0.65"), drivers()
    path = project(company((bad, good, good, good)))
    assert path.periods[0].income.ebit == 5
    assert path.periods[0].free_cash.tax_on_ebit == D(5) * D("0.25")
    assert path.periods[0].income.ordinary_tax == D(1) * D("0.25")


def burning(cash: str, limit: str, quarters: int = 4, **policy: object) -> Baseline:
    """Every quarter costs more than it earns: EBITDA −20, capex 10, no NWC change."""
    return company(
        (drivers(cogs="1"),) * quarters, cash=cash, tranches=(), revolver_limit=D(limit), **policy
    )


def test_the_revolver_covers_a_deficit_up_to_its_limit() -> None:
    path = project(burning("0", "100"))
    assert path.periods[0].cash_flow.revolver_net == 30
    assert path.periods[0].balance.cash == 0
    assert path.periods[0].balance.shortfall == 0


def test_negative_cash_never_appears_it_becomes_a_named_shortfall() -> None:
    path = project(burning("10", "30"))
    for period in path.periods:
        assert period.balance.cash >= 0
        assert period.balance.revolver <= 30
    last = path.periods[-1]
    assert last.balance.shortfall > 0
    assert "funding_shortfall" in last.alerts
    assert last.balance.net_debt == last.balance.revolver + last.balance.shortfall


def test_the_shortfall_costs_interest_at_the_rate_of_the_revolver() -> None:
    path = project(burning("0", "0"))
    assert path.periods[0].balance.shortfall == 30
    assert path.periods[1].income.interest_expense == D(30) * D("0.10") / 4


def test_surplus_repays_the_shortfall_first_and_then_the_revolver() -> None:
    bad, good = drivers(cogs="1"), drivers("400", cogs="0.2", nwc="0.025")
    opening = Opening(D(0), D(40), D(400), D(0), D(0), D(0), ())
    baseline = replace(
        burning("0", "20"),
        opening=opening,
        quarters=(bad, good, good, good),
    )
    path = project(baseline)
    assert path.periods[0].balance.revolver == 20
    assert path.periods[0].balance.shortfall == 10
    second = path.periods[1]
    assert second.cash_flow.shortfall_net == -10
    assert second.cash_flow.revolver_net == -20
    assert second.balance.debt == 0


def test_cash_below_the_minimum_is_flagged_but_is_not_a_shortfall() -> None:
    path = project(burning("50", "0", minimum_cash=D(40)))
    first = path.periods[0]
    assert first.balance.cash == 20
    assert first.alerts == ("below_minimum_cash",)


def test_dividends_are_paid_only_from_cash_above_the_minimum() -> None:
    path = project(company(cash="0", minimum_cash=D(10), dividend_payout=D(1)))
    first = path.periods[0]
    assert first.income.net_income == 12
    assert first.cash_flow.dividends == 2
    assert first.balance.cash == 10


def test_no_dividend_on_a_loss() -> None:
    path = project(burning("100", "0", dividend_payout=D(1)))
    assert all(period.cash_flow.dividends == 0 for period in path.periods)


def maturing() -> tuple[Tranche, ...]:
    return (Tranche("notes", D(200), D("0.08"), maturity_quarter=2),)


def test_a_maturity_rolls_at_the_marginal_rate_when_lenders_are_open() -> None:
    path = project(company(tranches=maturing()))
    second = path.periods[1]
    assert second.cash_flow.debt_repaid == 200
    assert second.cash_flow.debt_drawn == 200
    assert second.balance.term_debt == 200
    assert second.income.interest_expense == D(200) * D("0.09") / 4


def test_a_maturity_is_paid_from_cash_when_lenders_are_shut() -> None:
    path = project(company(tranches=maturing(), can_refinance=False))
    second = path.periods[1]
    assert second.cash_flow.debt_drawn == 0
    assert second.balance.term_debt == 0
    assert second.income.net_income == 15
    assert second.balance.shortfall == 200 - path.periods[0].balance.cash - 15
    assert second.income.interest_expense == 0


def test_two_loans_in_one_tranche_blend_the_rate_and_keep_the_earlier_maturity() -> None:
    plan = Plan(
        "x",
        (Borrow(1, "new", D(100), D("0.04"), 3), Borrow(2, "new", D(300), D("0.08"), None)),
    )
    path = project(company(), [plan])
    assert path.periods[1].income.interest_expense == D(4) + (D(4) + D(24)) / 4
    assert path.periods[2].cash_flow.debt_repaid == 400


def test_charge_and_payment_move_cash_only_when_paid() -> None:
    plan = Plan("x", (Charge(1, D(8)), Payment(3, D(8))))
    base, path = project(company()), project(company(), [plan])
    assert path.periods[0].balance.provision == 8
    assert path.periods[0].income.ebitda == base.periods[0].income.ebitda - 8
    assert path.periods[0].income.adjusted_ebitda == base.periods[0].income.adjusted_ebitda
    tax = D(8) * D("0.25")
    assert path.periods[0].balance.cash == base.periods[0].balance.cash + tax
    assert path.periods[2].balance.provision == 0


def test_paying_more_than_was_provided_is_refused() -> None:
    with pytest.raises(FinanceError, match="provision_overdrawn"):
        project(company(), [Plan("x", (Payment(1, D(1)),))])


def test_an_entry_outside_the_horizon_is_refused() -> None:
    with pytest.raises(FinanceError, match="outside_horizon"):
        project(company(), [Plan("x", (Flow(5, Line.ONE_OFF, D(1)),))])


def test_a_cost_cannot_go_below_zero() -> None:
    with pytest.raises(FinanceError, match="negative_line"):
        project(company(), [Plan("x", (Flow(1, Line.SGA, D(-11)),))])


def test_leverage_is_undefined_without_four_quarters_of_history() -> None:
    credit = project(company()).periods[0].credit
    assert credit.ttm_ebitda is None
    assert credit.leverage.reason == NO_HISTORY
    assert project(company()).periods[3].credit.ttm_ebitda == 120


def test_leverage_on_the_last_four_quarters() -> None:
    last = project(company()).periods[3]
    assert last.credit.leverage.value is not None
    assert abs(last.credit.leverage.value * 120 - last.balance.net_debt) < D("1e-20")
    assert last.credit.interest_cover.value == D(120) / 16


def test_leverage_is_undefined_at_ebitda_at_or_below_zero() -> None:
    baseline = company((drivers(cogs="0.8"),) * 4, max_leverage=D(3))
    last = project(baseline).periods[3]
    assert last.income.ebitda == 0
    assert last.credit.leverage.value is None
    assert last.credit.leverage.reason == NO_EBITDA


def test_net_debt_with_no_ebitda_breaks_the_covenant_though_the_ratio_is_undefined() -> None:
    baseline = company((drivers(cogs="0.8"),) * 4, cash="0", max_leverage=D(3))
    assert "leverage_breach" in project(baseline).periods[3].alerts


def test_net_cash_breaks_no_leverage_covenant() -> None:
    baseline = company(cash="1000", max_leverage=D(1))
    assert "leverage_breach" not in project(baseline).periods[3].alerts


def test_a_covenant_breach_is_flagged_above_the_limit() -> None:
    assert "leverage_breach" in project(company(max_leverage=D("0.4"))).periods[3].alerts
    assert "interest_cover_breach" in project(company(min_interest_cover=D(8))).periods[3].alerts


def test_reconciliation_catches_a_broken_statement() -> None:
    baseline = illustrative_baseline()
    path = project(baseline)
    last = path.periods[-1]
    broken = replace(last, balance=replace(last.balance, cash=last.balance.cash + 1))
    forged = StatementPath(
        path.currency, path.base_date, (*path.periods[:-1], broken), path.funding
    )
    with pytest.raises(FinanceError, match="reconciliation"):
        assert_reconciled(forged, baseline)


def test_reconciliation_catches_sources_that_differ_from_uses() -> None:
    baseline = illustrative_baseline()
    table = SourcesUses("deal", (("debt", D(9)),), (("price", D(10)),))
    path = project(baseline)
    forged = StatementPath(path.currency, path.base_date, path.periods, (table,))
    with pytest.raises(FinanceError, match="sources_equal_uses"):
        assert_reconciled(forged, baseline)


def test_the_example_reconciles_to_the_cent_and_much_tighter() -> None:
    baseline = illustrative_baseline()
    worst = max(abs(item.value) for item in residuals(project(baseline), baseline))
    assert worst < D("1e-30")


def test_the_same_input_gives_the_same_path() -> None:
    assert project(illustrative_baseline()) == project(illustrative_baseline())


def test_a_revolver_drawn_above_its_limit_is_an_impossible_opening() -> None:
    opening = Opening(D(0), D(0), D(0), D(0), D(0), D(0), (), revolver=D(5))
    with pytest.raises(FinanceError, match="impossible_debt"):
        replace(company(), opening=opening)
