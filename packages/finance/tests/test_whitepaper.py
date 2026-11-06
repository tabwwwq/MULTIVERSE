"""The numbers printed in docs/finance/financial-engine-whitepaper.md, section 14.

They describe an invented company. This test keeps the paper and the engine from drifting apart.
"""

from decimal import Decimal

import pytest

from multiverse_finance.engine import project
from multiverse_finance.example import (
    illustrative_baseline,
    illustrative_capital,
    illustrative_decisions,
)
from multiverse_finance.statements import StatementPath
from multiverse_finance.valuation import enterprise_value, equity_bridge

D = Decimal
HORIZON = 20
GROWTH = D("0.025")
BASE = illustrative_baseline(HORIZON)
CAPITAL = illustrative_capital()
PLANS = illustrative_decisions(BASE)


def rounded(value: Decimal | None) -> Decimal:
    assert value is not None
    return round(value, 1)


def value(path: StatementPath) -> Decimal:
    enterprise = enterprise_value(path, CAPITAL, GROWTH).enterprise_value
    assert enterprise is not None
    return enterprise


def last_year(path: StatementPath, name: str) -> Decimal:
    periods = path.periods[-4:]
    if name == "ebitda":
        return rounded(sum((period.income.ebitda for period in periods), D(0)))
    return rounded(sum((period.free_cash.fcff for period in periods), D(0)))


def test_the_baseline_of_the_paper() -> None:
    path = project(BASE)
    dcf = enterprise_value(path, CAPITAL, GROWTH)
    bridge = equity_bridge(dcf, BASE.opening)
    assert CAPITAL.wacc == D("0.0825")
    assert round(dcf.present_value, 2) == D("2093.88")
    assert dcf.terminal_value is not None
    assert round(dcf.terminal_value, 2) == D("10868.89")
    assert dcf.present_terminal is not None
    assert round(dcf.present_terminal, 2) == D("7312.16")
    assert dcf.enterprise_value is not None
    assert round(dcf.enterprise_value, 2) == D("9406.04")
    assert dcf.terminal_share.value is not None
    assert round(dcf.terminal_share.value, 3) == D("0.777")
    assert bridge.equity_value is not None
    assert round(bridge.equity_value, 2) == D("8506.04")


def test_three_flows_of_the_first_quarter_in_the_paper() -> None:
    first = project(BASE).periods[0]
    assert round(first.cash_flow.cfo, 2) == D("148.12")
    assert round(first.cash_flow.capex, 2) == D("51.00")
    assert round(first.free_cash.fcf_simple, 2) == D("97.12")
    assert round(first.free_cash.fcff, 2) == D("110.25")
    assert round(first.free_cash.fcfe, 2) == D("97.12")


@pytest.mark.parametrize(
    ("name", "change", "ebitda", "fcff", "lowest_cash"),
    [
        ("rnd_change", "-1346.7", "1038.8", "505.4", "569.8"),
        ("workforce_restructure", "1537.1", "1292.8", "695.8", "569.8"),
        ("acquisition", "309.8", "1338.2", "706.3", "345.6"),
        ("acquisition_failed", "-20.8", "1154.2", "592.0", "569.8"),
        ("divestiture", "-318.5", "1008.8", "524.0", "569.8"),
        ("capex_expansion", "2319.6", "1517.8", "806.4", "446.7"),
        ("debt_refinance", "0.0", "1154.2", "592.0", "569.8"),
    ],
)
def test_the_table_of_decisions_in_the_paper(
    name: str, change: str, ebitda: str, fcff: str, lowest_cash: str
) -> None:
    path = project(BASE, [PLANS[name]])
    assert rounded(value(path) - value(project(BASE))) == D(change)
    assert last_year(path, "ebitda") == D(ebitda)
    assert last_year(path, "fcff") == D(fcff)
    assert rounded(min(period.balance.cash for period in path.periods)) == D(lowest_cash)


def test_the_terminal_share_of_the_deal_in_the_paper() -> None:
    dcf = enterprise_value(project(BASE, [PLANS["acquisition"]]), CAPITAL, GROWTH)
    assert dcf.terminal_share.value is not None
    assert round(dcf.terminal_share.value, 3) == D("0.898")


def test_a_refinancing_leaves_ev_alone_and_moves_only_cash() -> None:
    path = project(BASE, [PLANS["debt_refinance"]])
    assert enterprise_value(path, CAPITAL, GROWTH) == enterprise_value(
        project(BASE), CAPITAL, GROWTH
    )
    assert path.periods[-1].balance.cash > project(BASE).periods[-1].balance.cash
