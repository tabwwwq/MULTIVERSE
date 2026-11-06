"""What the engine starts from: the opening balance sheet, the policy and the baseline drivers.

Conventions (docs/07):

- One currency and one base date per baseline. Quarter 1 is the first quarter after the date.
- Money is a Decimal in base units of the currency. Ratios are fractions of revenue.
- Rates are annual. A quarter of interest is a quarter of the rate on the balance.
- COGS, R&D and SG&A exclude D&A, which is its own line: so EBITDA = EBIT + D&A by construction.
- Leases are outside debt (OQ-13). Whoever needs them passes them as a senior claim in the bridge.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from multiverse_finance.exact import (
    EPSILON,
    ONE,
    ZERO,
    FinanceError,
    at_least,
    between,
    finite,
    share,
    whole,
)

CURRENCY = "USD"
"""D-04: the only currency of V1 to V3. Other currencies are refused, never converted here."""


@dataclass(frozen=True, slots=True)
class Tranche:
    """One loan. A bullet: the whole principal is due on the first day of its maturity quarter."""

    name: str
    principal: Decimal
    annual_rate: Decimal
    maturity_quarter: int | None = None
    floating: bool = False

    def __post_init__(self) -> None:
        at_least(self.principal, ZERO, f"tranche.{self.name}.principal")
        share(self.annual_rate, f"tranche.{self.name}.annual_rate")
        if self.maturity_quarter is not None:
            whole(self.maturity_quarter, 1, f"tranche.{self.name}.maturity_quarter")


@dataclass(frozen=True, slots=True)
class Opening:
    """The balance sheet at the base date. Equity is what is left, so it may be negative."""

    cash: Decimal
    trade_nwc: Decimal
    ppe: Decimal
    intangibles: Decimal
    goodwill: Decimal
    non_operating_assets: Decimal
    tranches: tuple[Tranche, ...]
    revolver: Decimal = ZERO
    provision: Decimal = ZERO
    tax_losses: Decimal = ZERO
    trailing_ebitda: tuple[Decimal, ...] = ()
    trailing_interest: tuple[Decimal, ...] = ()

    def __post_init__(self) -> None:
        at_least(self.cash, ZERO, "opening.cash")
        finite(self.trade_nwc, "opening.trade_nwc")
        for name in ("ppe", "intangibles", "goodwill", "non_operating_assets"):
            at_least(getattr(self, name), ZERO, f"opening.{name}")
        for name in ("revolver", "provision", "tax_losses"):
            at_least(getattr(self, name), ZERO, f"opening.{name}")
        for value in self.trailing_ebitda:
            finite(value, "opening.trailing_ebitda")
        for value in self.trailing_interest:
            at_least(value, ZERO, "opening.trailing_interest")
        names = [tranche.name for tranche in self.tranches]
        if len(set(names)) != len(names):
            raise FinanceError("duplicate_tranche", "opening.tranches", "names must be unique")

    @property
    def term_debt(self) -> Decimal:
        return sum((tranche.principal for tranche in self.tranches), ZERO)

    @property
    def equity(self) -> Decimal:
        assets = (
            self.cash
            + self.trade_nwc
            + self.ppe
            + self.intangibles
            + self.goodwill
            + self.non_operating_assets
        )
        return assets - self.term_debt - self.revolver - self.provision


@dataclass(frozen=True, slots=True)
class Policy:
    """How the company behaves, whatever the quarter."""

    tax_rate: Decimal
    depreciation_rate: Decimal
    amortization_rate: Decimal
    cash_yield: Decimal
    minimum_cash: Decimal
    revolver_limit: Decimal
    revolver_rate: Decimal
    marginal_debt_rate: Decimal
    can_refinance: bool = True
    dividend_payout: Decimal = ZERO
    max_leverage: Decimal | None = None
    min_interest_cover: Decimal | None = None

    def __post_init__(self) -> None:
        for name in (
            "tax_rate",
            "depreciation_rate",
            "amortization_rate",
            "cash_yield",
            "revolver_rate",
            "marginal_debt_rate",
            "dividend_payout",
        ):
            share(getattr(self, name), f"policy.{name}")
        at_least(self.minimum_cash, ZERO, "policy.minimum_cash")
        at_least(self.revolver_limit, ZERO, "policy.revolver_limit")
        if self.max_leverage is not None and finite(self.max_leverage, "policy.max_leverage") <= 0:
            raise FinanceError("out_of_range", "policy.max_leverage", "a limit is above 0")
        cover = self.min_interest_cover
        if cover is not None and finite(cover, "policy.min_interest_cover") <= 0:
            raise FinanceError("out_of_range", "policy.min_interest_cover", "a limit is above 0")


@dataclass(frozen=True, slots=True)
class Drivers:
    """One quarter of the baseline, before any decision."""

    segments: tuple[tuple[str, Decimal], ...]
    cogs_ratio: Decimal
    rd_ratio: Decimal
    sga_ratio: Decimal
    capex_ratio: Decimal
    nwc_ratio: Decimal
    rate_shift: Decimal = ZERO
    """Change of short rates since the base date: reaches floating debt, the revolver and rolls."""

    def __post_init__(self) -> None:
        if not self.segments:
            raise FinanceError("no_segments", "drivers.segments", "revenue needs a segment")
        for name, value in self.segments:
            at_least(value, ZERO, f"drivers.segments.{name}")
        for name in ("cogs_ratio", "rd_ratio", "sga_ratio", "capex_ratio"):
            at_least(getattr(self, name), ZERO, f"drivers.{name}")
        between(self.nwc_ratio, -ONE, ONE, "drivers.nwc_ratio")
        between(self.rate_shift, -ONE, ONE, "drivers.rate_shift")

    @property
    def revenue(self) -> Decimal:
        return sum((value for _, value in self.segments), ZERO)


@dataclass(frozen=True, slots=True)
class Baseline:
    """The path of a company with no decision taken."""

    currency: str
    base_date: date
    opening: Opening
    policy: Policy
    quarters: tuple[Drivers, ...]

    def __post_init__(self) -> None:
        if self.currency != CURRENCY:
            raise FinanceError(
                "currency", "baseline.currency", f"V1 to V3 support only {CURRENCY} (D-04)"
            )
        if not self.quarters:
            raise FinanceError("empty_horizon", "baseline.quarters", "at least one quarter")
        if self.opening.revolver > self.policy.revolver_limit + EPSILON:
            raise FinanceError(
                "impossible_debt", "opening.revolver", "drawn above the limit of the revolver"
            )

    @property
    def horizon(self) -> int:
        return len(self.quarters)
