"""The entries a decision leaves in the books.

A decision never edits a KPI. It compiles into entries like these, and the engine books them
through the three statements, so EBITDA, cash and value can only move together. Every amount is
positive in the direction its name says; a Flow may be negative (a saving is a negative cost).
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from multiverse_finance.exact import ONE, ZERO, FinanceError, at_least, finite, share, whole


class Line(StrEnum):
    REVENUE = "revenue"
    COGS = "cogs"
    RD_EXPENSE = "rd_expense"
    SGA = "sga"
    ONE_OFF = "one_off"
    """Expensed and paid in the quarter. Inside EBITDA, added back in adjusted EBITDA."""
    FINANCING_FEE = "financing_fee"
    """Expensed and paid in the quarter, below EBIT."""
    CONSTRUCTION = "construction"
    """Cash into construction in progress: an asset that does not depreciate yet."""


@dataclass(frozen=True, slots=True)
class Flow:
    quarter: int
    line: Line
    amount: Decimal
    segment: str | None = None

    def __post_init__(self) -> None:
        finite(self.amount, f"flow.{self.line}")
        if (self.line is Line.REVENUE) != (self.segment is not None):
            raise FinanceError(
                "segment", f"flow.{self.line}", "revenue, and only it, has a segment"
            )


@dataclass(frozen=True, slots=True)
class Charge:
    """A restructuring provision: expensed now, paid later."""

    quarter: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Payment:
    """Cash paid against the provision: no expense, it was recognized by the charge."""

    quarter: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Capitalize:
    """Development cost paid in cash and kept as an intangible, amortized in a straight line."""

    quarter: int
    amount: Decimal
    life_quarters: int


@dataclass(frozen=True, slots=True)
class InService:
    """Construction in progress starts to be used: depreciation starts this quarter."""

    quarter: int
    amount: Decimal
    life_quarters: int


@dataclass(frozen=True, slots=True)
class Borrow:
    """New term debt, on the first day of the quarter."""

    quarter: int
    tranche: str
    amount: Decimal
    annual_rate: Decimal
    maturity_quarter: int | None = None


@dataclass(frozen=True, slots=True)
class Retire:
    """Term debt repaid before its maturity, on the first day, oldest tranche first."""

    quarter: int
    amount: Decimal
    keep: str
    """The tranche this repayment must not touch: the one that replaces the debt."""


@dataclass(frozen=True, slots=True)
class Issue:
    """New equity for cash, at fair value: value of existing holders is not diluted here."""

    quarter: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Purchase:
    """A business bought on the first day, cash-free and debt-free. Goodwill is the rest."""

    quarter: int
    price: Decimal
    ppe: Decimal
    trade_nwc: Decimal
    intangibles: Decimal
    intangibles_life_quarters: int

    @property
    def goodwill(self) -> Decimal:
        return self.price - self.ppe - self.trade_nwc - self.intangibles


@dataclass(frozen=True, slots=True)
class Sale:
    """A share of the business leaves on the first day, with that share of its book assets."""

    quarter: int
    fraction: Decimal
    proceeds: Decimal
    separation_cost: Decimal
    tax_rate_on_gain: Decimal
    paydown_share: Decimal
    distribution_share: Decimal

    def __post_init__(self) -> None:
        share(self.fraction, "sale.fraction")
        at_least(self.proceeds, ZERO, "sale.proceeds")
        at_least(self.separation_cost, ZERO, "sale.separation_cost")
        share(self.tax_rate_on_gain, "sale.tax_rate_on_gain")
        share(self.paydown_share, "sale.paydown_share")
        share(self.distribution_share, "sale.distribution_share")
        if self.paydown_share + self.distribution_share > ONE:
            raise FinanceError("shares_sum", "sale", "the shares of proceeds exceed 100%")


Entry = Flow | Charge | Payment | Capitalize | InService | Borrow | Retire | Issue | Purchase | Sale


@dataclass(frozen=True, slots=True)
class SourcesUses:
    """One funding table: where the money comes from and where it goes."""

    label: str
    sources: tuple[tuple[str, Decimal], ...]
    uses: tuple[tuple[str, Decimal], ...]

    @property
    def residual(self) -> Decimal:
        return sum((value for _, value in self.sources), ZERO) - sum(
            (value for _, value in self.uses), ZERO
        )


@dataclass(frozen=True, slots=True)
class Plan:
    """One decision, ready to book. ``notes`` say what was assumed on the way."""

    decision: str
    entries: tuple[Entry, ...]
    funding: tuple[SourcesUses, ...] = ()
    notes: tuple[str, ...] = ()


def check_entry(entry: Entry, horizon: int) -> None:
    """Quarter inside the horizon and finite amounts. Flows may be negative, the rest not."""
    path = type(entry).__name__.lower()
    if not 1 <= entry.quarter <= horizon:
        raise FinanceError("outside_horizon", path, f"quarter {entry.quarter} of {horizon}")
    if isinstance(entry, Charge | Payment | Capitalize | InService | Borrow | Retire | Issue):
        at_least(entry.amount, ZERO, f"{path}.amount")
    if isinstance(entry, Capitalize | InService):
        whole(entry.life_quarters, 1, f"{path}.life_quarters")
    if isinstance(entry, Borrow):
        share(entry.annual_rate, f"{path}.annual_rate")
    if isinstance(entry, Purchase):
        at_least(entry.price, ZERO, f"{path}.price")
        at_least(entry.ppe, ZERO, f"{path}.ppe")
        finite(entry.trade_nwc, f"{path}.trade_nwc")
        at_least(entry.intangibles, ZERO, f"{path}.intangibles")
        whole(entry.intangibles_life_quarters, 1, f"{path}.intangibles_life_quarters")
        if entry.goodwill < 0:
            raise FinanceError(
                "negative_goodwill", path, "identified net assets exceed the price paid"
            )
