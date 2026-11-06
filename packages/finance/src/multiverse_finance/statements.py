"""What the engine returns: the three statements of each quarter and what follows from them."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from multiverse_finance.exact import Ratio
from multiverse_finance.ledger import SourcesUses


@dataclass(frozen=True, slots=True)
class Income:
    segments: tuple[tuple[str, Decimal], ...]
    revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    rd_expense: Decimal
    sga: Decimal
    one_off: Decimal
    ebitda: Decimal
    """Calculated: EBIT + D&A, after one-off items. Not a reported number (D-05)."""
    adjusted_ebitda: Decimal
    """EBITDA + one-off items. The only adjustment, and the engine's own definition."""
    depreciation: Decimal
    amortization: Decimal
    ebit: Decimal
    interest_expense: Decimal
    interest_income: Decimal
    financing_fees: Decimal
    disposal_gain: Decimal
    pre_tax_income: Decimal
    ordinary_tax: Decimal
    disposal_tax: Decimal
    net_income: Decimal

    @property
    def d_and_a(self) -> Decimal:
        return self.depreciation + self.amortization


@dataclass(frozen=True, slots=True)
class CashFlow:
    delta_nwc: Decimal
    """Rise of trade NWC less rise of the provision, without what was bought or sold."""
    cfo: Decimal
    capex: Decimal
    """Positive means spent: PP&E, construction and capitalized development."""
    acquisitions: Decimal
    disposal_proceeds: Decimal
    cfi: Decimal
    debt_drawn: Decimal
    debt_repaid: Decimal
    revolver_net: Decimal
    shortfall_net: Decimal
    equity_issued: Decimal
    dividends: Decimal
    distributions: Decimal
    cff: Decimal
    net_change: Decimal


@dataclass(frozen=True, slots=True)
class Balance:
    cash: Decimal
    trade_nwc: Decimal
    ppe: Decimal
    intangibles: Decimal
    goodwill: Decimal
    non_operating_assets: Decimal
    provision: Decimal
    term_debt: Decimal
    revolver: Decimal
    shortfall: Decimal
    """Money the company needed and no lender gave. Cash never goes below zero silently."""
    equity: Decimal

    @property
    def assets(self) -> Decimal:
        return (
            self.cash
            + self.trade_nwc
            + self.ppe
            + self.intangibles
            + self.goodwill
            + self.non_operating_assets
        )

    @property
    def liabilities(self) -> Decimal:
        return self.provision + self.debt

    @property
    def debt(self) -> Decimal:
        return self.term_debt + self.revolver + self.shortfall

    @property
    def net_debt(self) -> Decimal:
        return self.debt - self.cash


@dataclass(frozen=True, slots=True)
class FreeCash:
    """Three different quantities. Only FCFF goes with WACC."""

    tax_on_ebit: Decimal
    """Tax with no debt at all, with its own tax losses."""
    fcff_operating: Decimal
    """EBIT − tax on EBIT + D&A − CAPEX − ΔNWC (docs/07)."""
    transactions: Decimal
    """Disposal proceeds after their tax, less the price of what was bought."""
    fcff: Decimal
    """Unlevered: what all capital providers can take out. The input of EV."""
    fcff_recurring: Decimal
    """FCFF without transactions, one-off cash and construction: the input of terminal value."""
    fcf_simple: Decimal
    """CFO − CAPEX: after interest, before debt flows. Never discounted at WACC."""
    tax_shield: Decimal
    net_borrowing: Decimal
    fcfe: Decimal
    """Levered: CFO − CAPEX + transactions + net borrowing. Goes with cost of equity."""


@dataclass(frozen=True, slots=True)
class Credit:
    ttm_ebitda: Decimal | None
    net_debt: Decimal
    leverage: Ratio
    interest_cover: Ratio


@dataclass(frozen=True, slots=True)
class Period:
    quarter: int
    income: Income
    cash_flow: CashFlow
    balance: Balance
    free_cash: FreeCash
    credit: Credit
    tax_losses: Decimal
    alerts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StatementPath:
    """One reconciled path. ``project`` never returns one that does not reconcile."""

    currency: str
    base_date: date
    periods: tuple[Period, ...]
    funding: tuple[SourcesUses, ...]
