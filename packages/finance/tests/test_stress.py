"""Stress cases of docs/07: each still reconciles, and each hurts where it should."""

from decimal import Decimal

import pytest

from multiverse_finance.engine import project
from multiverse_finance.exact import FinanceError
from multiverse_finance.example import illustrative_baseline
from multiverse_finance.interventions import (
    AcquisitionTerms,
    Funding,
    Timing,
    acquisition,
)
from multiverse_finance.stress import (
    covenant,
    margin_compression,
    maturity_wall,
    rate_shock,
    refinancing_closed,
    revenue_shock,
    working_capital_absorption,
)

D = Decimal
BASE = illustrative_baseline()
PATH = project(BASE)


def test_revenue_shock_of_twenty_percent() -> None:
    path = project(revenue_shock(BASE, D("0.2"), start=3))
    assert path.periods[1].income.revenue == PATH.periods[1].income.revenue
    assert path.periods[2].income.revenue == PATH.periods[2].income.revenue * D("0.8")
    assert path.periods[-1].balance.cash < PATH.periods[-1].balance.cash


def test_a_fall_above_one_hundred_percent_is_refused() -> None:
    with pytest.raises(FinanceError, match="out_of_range"):
        revenue_shock(BASE, D("1.2"))


def test_margin_compression_takes_points_off_the_gross_margin() -> None:
    path = project(margin_compression(BASE, D("0.03")))
    first, base = path.periods[0].income, PATH.periods[0].income
    assert first.gross_profit == base.gross_profit - D("0.03") * base.revenue


def test_rates_up_two_hundred_points_reach_floating_debt_only_until_maturity() -> None:
    path = project(rate_shock(BASE, D("0.02")))
    first = path.periods[0].income.interest_expense - PATH.periods[0].income.interest_expense
    assert first == D(500) * D("0.02") / 4
    eighth = path.periods[7].income.interest_expense - PATH.periods[7].income.interest_expense
    assert eighth == D(1500) * D("0.02") / 4


def test_working_capital_absorption_costs_cash_not_ebitda() -> None:
    path = project(working_capital_absorption(BASE, D("0.05"), start=2))
    second, base = path.periods[1], PATH.periods[1]
    assert second.income.ebitda == base.income.ebitda
    assert second.cash_flow.delta_nwc > base.cash_flow.delta_nwc
    assert second.free_cash.fcff < base.free_cash.fcff


def test_a_closed_refinancing_market_eats_cash_at_maturity() -> None:
    path = project(refinancing_closed(BASE))
    maturity = path.periods[7]
    assert maturity.cash_flow.debt_repaid == 1000
    assert maturity.cash_flow.debt_drawn == 0
    assert maturity.balance.term_debt == 500


def test_a_closed_market_after_a_bad_year_leaves_a_named_shortfall() -> None:
    weak = margin_compression(revenue_shock(refinancing_closed(BASE), D("0.45")), D("0.15"))
    path = project(weak)
    maturity = path.periods[7]
    assert maturity.balance.revolver == 300
    assert maturity.balance.shortfall > 0
    assert "funding_shortfall" in maturity.alerts
    assert all(period.balance.cash >= 0 for period in path.periods)


def test_a_tighter_covenant_is_breached_on_the_same_path() -> None:
    assert "leverage_breach" not in PATH.periods[0].alerts
    assert "leverage_breach" in project(covenant(BASE, D("0.5"))).periods[0].alerts


def terms(**changes: object) -> AcquisitionTerms:
    settings: dict[str, object] = {
        "timing": Timing(1, ramp_quarters=2),
        "price": D(2400),
        "target_revenue": D(1000),
        "target_ebitda_margin": D("0.15"),
        "deal_cost_fraction": D("0.02"),
        "integration_cost_fraction": D("0.05"),
        "cost_synergy_fraction": D("0.04"),
        "new_debt_rate": D("0.08"),
        "funding": Funding(D(0), D(1), D(0)),
    } | changes
    return AcquisitionTerms(**settings)  # type: ignore[arg-type]


def test_acquisition_failure_keeps_the_debt_undrawn() -> None:
    path = project(BASE, [acquisition(BASE, terms(completed=False))])
    assert path.periods[0].balance.term_debt == 1500
    assert path.periods[0].income.one_off == 48


def test_delayed_synergies_cost_ebitda() -> None:
    on_time = project(BASE, [acquisition(BASE, terms())])
    late = project(BASE, [acquisition(BASE, terms(synergy_delay_quarters=4))])
    assert late.periods[3].income.ebitda < on_time.periods[3].income.ebitda
    assert late.periods[-1].income.ebitda == on_time.periods[-1].income.ebitda


def test_a_debt_funded_deal_with_a_revenue_shock_breaks_the_covenant_and_still_reconciles() -> None:
    weak = revenue_shock(BASE, D("0.2"))
    path = project(weak, [acquisition(weak, terms())])
    assert any("leverage_breach" in period.alerts for period in path.periods)


def test_a_maturity_wall_gives_a_date_to_debt_that_had_none() -> None:
    wall = maturity_wall(BASE, 6)
    dates = {tranche.name: tranche.maturity_quarter for tranche in wall.opening.tranches}
    assert dates == {"senior_notes": 8, "term_loan": 6}
    path = project(refinancing_closed(wall))
    assert path.periods[5].cash_flow.debt_repaid == 500
