"""Reconciliation: identities recomputed from the finished statements, quarter by quarter.

The engine rolls each stock by its own rule. The balance sheet check is therefore a real test:
assets, liabilities and equity are never derived from one another.
"""

from dataclasses import dataclass
from decimal import Decimal

from multiverse_finance.exact import ZERO, FinanceError, exact
from multiverse_finance.model import Baseline
from multiverse_finance.statements import Period, StatementPath

TOLERANCE = Decimal("0.01")
"""One cent. Exact shares leave remainders far below this; a booking error does not."""


@dataclass(frozen=True, slots=True)
class Residual:
    quarter: int
    identity: str
    value: Decimal


def _income(period: Period) -> dict[str, Decimal]:
    i = period.income
    return {
        "segments_add_to_revenue": sum((v for _, v in i.segments), ZERO) - i.revenue,
        "gross_profit": i.revenue - i.cogs - i.gross_profit,
        "ebitda": i.gross_profit - i.rd_expense - i.sga - i.one_off - i.ebitda,
        "ebit_plus_d_and_a": i.ebit + i.d_and_a - i.ebitda,
        "adjusted_ebitda": i.ebitda + i.one_off - i.adjusted_ebitda,
        "net_income": (
            i.ebit
            - i.interest_expense
            + i.interest_income
            - i.financing_fees
            + i.disposal_gain
            - i.ordinary_tax
            - i.disposal_tax
            - i.net_income
        ),
    }


def _cash(period: Period) -> dict[str, Decimal]:
    i, c, f = period.income, period.cash_flow, period.free_cash
    return {
        "cfo": i.net_income + i.d_and_a - i.disposal_gain - c.delta_nwc - c.cfo,
        "cfi": c.disposal_proceeds - c.capex - c.acquisitions - c.cfi,
        "cash_flow_adds_up": c.cfo + c.cfi + c.cff - c.net_change,
        "fcff": (
            i.ebit
            - f.tax_on_ebit
            + i.d_and_a
            - c.capex
            - c.delta_nwc
            + c.disposal_proceeds
            - i.disposal_tax
            - c.acquisitions
            - f.fcff
        ),
        "fcf_simple": c.cfo - c.capex - f.fcf_simple,
        "fcff_to_fcfe": (
            f.fcff
            - i.interest_expense
            + i.interest_income
            - i.financing_fees
            + f.tax_shield
            + f.net_borrowing
            - f.fcfe
        ),
        "fcfe_to_cash": f.fcfe + c.equity_issued - c.dividends - c.distributions - c.net_change,
    }


@exact
def residuals(path: StatementPath, baseline: Baseline) -> tuple[Residual, ...]:
    """Every identity of every quarter, and of every funding table, as a residual."""
    found = [
        Residual(0, f"sources_equal_uses:{table.label}", table.residual) for table in path.funding
    ]
    opening = baseline.opening
    cash, debt, equity = opening.cash, opening.term_debt + opening.revolver, opening.equity
    for period in path.periods:
        b, c = period.balance, period.cash_flow
        values = _income(period) | _cash(period)
        values |= {
            "assets_equal_liabilities_and_equity": b.assets - b.liabilities - b.equity,
            "cash_roll": cash + c.net_change - b.cash,
            "debt_roll": debt + period.free_cash.net_borrowing - b.debt,
            "equity_roll": (
                equity
                + period.income.net_income
                + c.equity_issued
                - c.dividends
                - c.distributions
                - b.equity
            ),
            "cash_not_negative": min(b.cash, ZERO),
            "revolver_within_limit": max(b.revolver - baseline.policy.revolver_limit, ZERO),
        }
        found.extend(Residual(period.quarter, name, value) for name, value in values.items())
        cash, debt, equity = b.cash, b.debt, b.equity
    return tuple(found)


def assert_reconciled(
    path: StatementPath, baseline: Baseline, tolerance: Decimal = TOLERANCE
) -> None:
    """Raise on the first residual above the tolerance: a path that fails never leaves."""
    for residual in residuals(path, baseline):
        if abs(residual.value) > tolerance:
            raise FinanceError(
                "reconciliation",
                f"Q{residual.quarter}.{residual.identity}",
                f"residual {residual.value} is above {tolerance}",
            )
