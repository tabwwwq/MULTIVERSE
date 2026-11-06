"""DCF and the bridge against answers known in advance."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from multiverse_finance.engine import project
from multiverse_finance.exact import FinanceError, exact
from multiverse_finance.example import illustrative_baseline, illustrative_capital
from multiverse_finance.stress import revenue_shock
from multiverse_finance.valuation import (
    NO_TERMINAL,
    CapitalCost,
    discount_factor,
    discounted,
    enterprise_value,
    equity_bridge,
)

D = Decimal
CENT = D("1e-20")
ZERO_YEAR = (D(0), D(0), D(0))


def close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) < CENT


def test_wacc_from_its_parts() -> None:
    capital = illustrative_capital()
    assert capital.cost_of_equity == D("0.095")
    assert capital.wacc == D("0.75") * D("0.095") + D("0.25") * D("0.06") * D("0.75")


def test_a_flat_perpetuity_is_worth_flow_over_rate() -> None:
    dcf = discounted([*ZERO_YEAR, D(100)], [*ZERO_YEAR, D(100)], D("0.10"), D(0))
    assert dcf.terminal_value is not None
    assert dcf.enterprise_value is not None
    assert close(dcf.terminal_value, D(1000))
    assert close(dcf.enterprise_value, D(1000))


def test_a_growing_perpetuity_is_gordon() -> None:
    dcf = discounted([*ZERO_YEAR, D(100)], [*ZERO_YEAR, D(100)], D("0.10"), D("0.02"))
    assert dcf.terminal_value is not None
    assert dcf.enterprise_value is not None
    assert close(dcf.terminal_value, D(102) / D("0.08"))
    assert close(dcf.enterprise_value, D(100) / D("0.08"))


def test_quarterly_factors_come_from_the_effective_annual_rate_not_a_quarter_of_it() -> None:
    @exact
    def compounded() -> Decimal:
        return discount_factor(1, D("0.10")) ** 4

    assert close(compounded(), 1 / D("1.10"))
    assert discount_factor(1, D("0.10")) != 1 / (1 + D("0.10") / 4)


@given(
    st.lists(st.integers(1, 500), min_size=4, max_size=4),
    st.integers(1, 3),
    st.integers(5, 15),
    st.integers(0, 4),
)
def test_a_seasonal_stream_has_the_same_value_at_any_horizon(
    season: list[int], years: int, rate: int, growth: int
) -> None:
    """The perpetuity continues the stream exactly, so where it starts cannot change the value."""
    r, g = D(rate) / 100, D(growth) / 100
    short = [D(value) for value in season]
    long = [flow * (1 + g) ** year for year in range(years + 1) for flow in short]
    first = discounted(short, short, r, g)
    second = discounted(long, long[-4:], r, g)
    assert first.enterprise_value is not None
    assert second.enterprise_value is not None
    assert abs(first.enterprise_value - second.enterprise_value) < D("1e-20")


@pytest.mark.parametrize(("rate", "growth"), [("0.03", "0.03"), ("0.03", "0.05")])
def test_wacc_at_or_below_growth_is_refused(rate: str, growth: str) -> None:
    with pytest.raises(FinanceError, match="wacc_not_above_growth"):
        discounted([D(1)] * 4, [D(1)] * 4, D(rate), D(growth))


@pytest.mark.parametrize(
    ("rate", "growth", "code"),
    [
        ("NaN", "0.02", "not_finite"),
        ("0.08", "Infinity", "not_finite"),
        ("0", "-0.01", "rate_not_positive"),
        ("-0.05", "-0.1", "rate_not_positive"),
        ("0.08", "-1", "out_of_range"),
    ],
)
def test_impossible_rates_are_refused(rate: str, growth: str, code: str) -> None:
    with pytest.raises(FinanceError, match=code):
        discounted([D(1)] * 4, [D(1)] * 4, D(rate), D(growth))


def test_a_nan_flow_is_refused() -> None:
    with pytest.raises(FinanceError, match="not_finite"):
        discounted([D("NaN")] * 4, [D(1)] * 4, D("0.08"), D(0))


def test_a_terminal_year_needs_four_quarters() -> None:
    with pytest.raises(FinanceError, match="short_horizon"):
        discounted([D(1)] * 3, [D(1)] * 3, D("0.08"), D(0))


def test_a_path_shorter_than_a_year_has_no_terminal_year() -> None:
    path = project(illustrative_baseline(3))
    with pytest.raises(FinanceError, match="short_horizon"):
        enterprise_value(path, illustrative_capital(), D("0.02"))


def test_negative_recurring_flow_leaves_ev_undefined_instead_of_a_negative_perpetuity() -> None:
    dcf = discounted([D(10)] * 4, [D(-1)] * 4, D("0.08"), D(0))
    assert dcf.enterprise_value is None
    assert dcf.terminal_value is None
    assert dcf.present_value > 0
    assert dcf.reason == NO_TERMINAL
    bridge = equity_bridge(dcf, illustrative_baseline().opening)
    assert bridge.equity_value is None
    assert bridge.reason == NO_TERMINAL


def test_terminal_share_is_undefined_when_ev_is_not_positive() -> None:
    dcf = discounted([D(-5000)] * 4, [D(1)] * 4, D("0.08"), D(0))
    assert dcf.enterprise_value is not None
    assert dcf.enterprise_value < 0
    assert dcf.terminal_share.value is None


def test_ev_reads_fcff_and_wacc_and_shows_the_terminal_share() -> None:
    path = project(illustrative_baseline())
    capital = illustrative_capital()
    dcf = enterprise_value(path, capital, D("0.025"))
    assert dcf.enterprise_value is not None
    assert dcf.present_terminal is not None
    assert dcf.terminal_share.value is not None
    assert close(dcf.enterprise_value, dcf.present_value + dcf.present_terminal)
    assert D(0) < dcf.terminal_share.value < D(1)


def test_discounting_cfo_minus_capex_would_give_another_number() -> None:
    """Why ``enterprise_value`` reads a path and not any list of flows."""
    path = project(illustrative_baseline())
    capital = illustrative_capital()
    simple = [period.free_cash.fcf_simple for period in path.periods]
    mixed = discounted(simple, simple[-4:], capital.wacc, D("0.025"))
    proper = enterprise_value(path, capital, D("0.025"))
    assert mixed.enterprise_value != proper.enterprise_value


def test_bridge_by_hand() -> None:
    company = illustrative_baseline()
    dcf = discounted([*ZERO_YEAR, D(100)], [*ZERO_YEAR, D(100)], D("0.10"), D(0))
    bridge = equity_bridge(dcf, company.opening, other_senior_claims=D(50))
    assert bridge.debt == 1500
    assert bridge.cash == 500
    assert bridge.non_operating_assets == 100
    assert bridge.equity_value is not None
    assert close(bridge.equity_value, D(1000) - 1500 + 500 - 50 + 100)


def test_ev_and_equity_are_different_outputs() -> None:
    company = illustrative_baseline()
    dcf = enterprise_value(project(company), illustrative_capital(), D("0.025"))
    bridge = equity_bridge(dcf, company.opening)
    assert bridge.equity_value != bridge.enterprise_value


def test_a_negative_claim_is_refused() -> None:
    company = illustrative_baseline()
    dcf = enterprise_value(project(company), illustrative_capital(), D("0.025"))
    with pytest.raises(FinanceError, match="out_of_range"):
        equity_bridge(dcf, company.opening, other_senior_claims=D(-1))


@pytest.mark.parametrize(
    ("field", "value"),
    [("beta", D(-1)), ("tax_rate", D("1.2")), ("debt_weight", D("NaN")), ("risk_free", D("-0.1"))],
)
def test_impossible_capital_settings_are_refused(field: str, value: Decimal) -> None:
    good = {
        "risk_free": D("0.04"),
        "equity_risk_premium": D("0.05"),
        "beta": D(1),
        "pre_tax_cost_of_debt": D("0.06"),
        "tax_rate": D("0.25"),
        "debt_weight": D("0.2"),
    }
    with pytest.raises(FinanceError):
        CapitalCost(**(good | {field: value}))


def test_a_lower_revenue_path_is_worth_less() -> None:
    capital = illustrative_capital()
    base = enterprise_value(project(illustrative_baseline()), capital, D("0.025"))
    low = enterprise_value(
        project(revenue_shock(illustrative_baseline(), D("0.2"))), capital, D("0.025")
    )
    assert base.enterprise_value is not None
    assert low.enterprise_value is not None
    assert low.enterprise_value < base.enterprise_value
