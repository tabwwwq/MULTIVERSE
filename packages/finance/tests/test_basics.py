"""Bad numbers are refused, undefined ratios say why, schedules land where they should."""

import subprocess
import sys
from decimal import Decimal, getcontext, localcontext

import pytest
from hypothesis import given
from hypothesis import strategies as st

from multiverse_finance.exact import FinanceError, finite, ratio, share
from multiverse_finance.example import illustrative_baseline
from multiverse_finance.model import Baseline, Opening
from multiverse_finance.schedules import ramp, shifted, spread

D = Decimal


@pytest.mark.parametrize("value", [D("NaN"), D("Infinity"), D("-Infinity")])
def test_a_number_that_is_not_finite_is_refused(value: Decimal) -> None:
    with pytest.raises(FinanceError, match="not_finite"):
        finite(value, "x")


def test_a_float_is_refused_because_it_is_not_exact() -> None:
    with pytest.raises(FinanceError, match="not_decimal"):
        finite(0.1, "x")


def test_a_share_lives_between_zero_and_one() -> None:
    assert share(D("0.4"), "x") == D("0.4")
    with pytest.raises(FinanceError, match="out_of_range"):
        share(D("1.01"), "x")


@pytest.mark.parametrize("denominator", [D(0), D(-5)])
def test_a_ratio_has_no_value_at_a_zero_or_negative_denominator(denominator: Decimal) -> None:
    undefined = ratio(D(10), denominator, "why")
    assert undefined.value is None
    assert undefined.reason == "why"


def test_a_ratio_with_a_positive_denominator() -> None:
    assert ratio(D(10), D(4), "why").value == D("2.5")


def test_an_opening_with_nan_cash_is_refused() -> None:
    with pytest.raises(FinanceError, match="not_finite"):
        Opening(D("NaN"), D(0), D(0), D(0), D(0), D(0), ())


def test_another_currency_is_refused_not_converted() -> None:
    company = illustrative_baseline()
    with pytest.raises(FinanceError, match=r"\[currency\]"):
        Baseline("EUR", company.base_date, company.opening, company.policy, company.quarters)


def test_ramp_climbs_in_a_straight_line() -> None:
    assert ramp(6, 3, 2) == (D(0), D(0), D("0.5"), D(1), D(1), D(1))


@pytest.mark.parametrize("quarters", [0, 1])
def test_ramp_of_zero_or_one_quarter_is_immediate(quarters: int) -> None:
    assert ramp(3, 2, quarters) == (D(0), D(1), D(1))


@given(st.integers(1, 40), st.integers(1, 45), st.integers(0, 20))
def test_ramp_never_falls_and_stays_between_zero_and_one(
    horizon: int, start: int, quarters: int
) -> None:
    shares = ramp(horizon, start, quarters)
    assert len(shares) == horizon
    assert all(D(0) <= value <= D(1) for value in shares)
    assert list(shares) == sorted(shares)
    assert all(value == 0 for value in shares[: start - 1])
    if start + max(quarters, 1) - 1 <= horizon:
        assert shares[-1] == 1


def test_shifted_moves_later_and_keeps_the_horizon() -> None:
    assert shifted((D(1), D(2), D(3)), 1) == (D(0), D(1), D(2))
    assert shifted((D(1), D(2)), 9) == (D(0), D(0))


@given(st.integers(1, 30), st.integers(0, 40))
def test_shifted_loses_only_what_leaves_the_horizon(length: int, quarters: int) -> None:
    series = tuple(D(n + 1) for n in range(length))
    moved = shifted(series, quarters)
    assert len(moved) == length
    assert sum(moved) == sum(series[: max(length - quarters, 0)])


def test_spread_splits_evenly_and_zero_means_at_once() -> None:
    assert spread(D(90), 2, 3, 5) == (D(0), D(30), D(30), D(30), D(0))
    assert spread(D(90), 2, 0, 3) == (D(0), D(90), D(0))


@given(st.integers(1, 30), st.integers(0, 12))
def test_spread_inside_the_horizon_keeps_the_whole_amount(start: int, quarters: int) -> None:
    horizon = start + max(quarters, 1) + 2
    assert abs(sum(spread(D(1000), start, quarters, horizon)) - 1000) < D("1e-20")


def test_spread_past_the_horizon_drops_what_falls_outside() -> None:
    assert sum(spread(D(100), 3, 4, 4)) == 50


def test_the_engine_does_not_depend_on_the_callers_decimal_context() -> None:
    from multiverse_finance.engine import project

    baseline = illustrative_baseline()
    wide = project(baseline)
    with localcontext() as context:
        context.prec = 6
        assert illustrative_baseline() == baseline
        narrow = project(baseline)
    assert narrow == wide
    assert getcontext().prec != 6


def test_finance_imports_no_web_or_ml_framework() -> None:
    code = (
        "import sys, multiverse_finance.engine, multiverse_finance.valuation,"
        "multiverse_finance.decisions;"
        "print(sorted({'torch','numpy','pandas','fastapi','sklearn'} & set(sys.modules)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
