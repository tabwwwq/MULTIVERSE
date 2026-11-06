"""Value from a reconciled path: WACC, DCF and the bridge from enterprise to equity value.

``enterprise_value`` takes a path, not a list of numbers: FCFF is the only flow it can read, so
CFO − CAPEX or FCFE cannot be discounted at WACC by mistake. A model number, never a verified
market value.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from multiverse_finance.exact import (
    ONE,
    QUARTERS_PER_YEAR,
    ZERO,
    FinanceError,
    Ratio,
    at_least,
    exact,
    finite,
    ratio,
    share,
)
from multiverse_finance.model import Opening
from multiverse_finance.statements import StatementPath

NO_TERMINAL = "undefined: the last four quarters of recurring FCFF are not positive"
NO_EV = "undefined: enterprise value <= 0"
NO_EBITDA = "undefined: EBITDA of the last four quarters is not positive"


@dataclass(frozen=True, slots=True)
class CapitalCost:
    """WACC from its parts, each visible. Target weights, not book weights."""

    risk_free: Decimal
    equity_risk_premium: Decimal
    beta: Decimal
    pre_tax_cost_of_debt: Decimal
    tax_rate: Decimal
    debt_weight: Decimal

    def __post_init__(self) -> None:
        share(self.risk_free, "capital.risk_free")
        share(self.equity_risk_premium, "capital.equity_risk_premium")
        at_least(self.beta, ZERO, "capital.beta")
        share(self.pre_tax_cost_of_debt, "capital.pre_tax_cost_of_debt")
        share(self.tax_rate, "capital.tax_rate")
        share(self.debt_weight, "capital.debt_weight")

    @property
    def cost_of_equity(self) -> Decimal:
        return self.risk_free + self.beta * self.equity_risk_premium

    @property
    def wacc(self) -> Decimal:
        after_tax_debt = self.pre_tax_cost_of_debt * (ONE - self.tax_rate)
        return (ONE - self.debt_weight) * self.cost_of_equity + self.debt_weight * after_tax_debt


@dataclass(frozen=True, slots=True)
class Dcf:
    """Present value at the base date. Without a terminal value, EV is undefined and says why."""

    present_value: Decimal
    terminal_value: Decimal | None
    present_terminal: Decimal | None
    enterprise_value: Decimal | None
    terminal_share: Ratio
    reason: str | None = None


def discount_factor(quarter: int, annual_rate: Decimal) -> Decimal:
    """End of quarter ``quarter``, from an effective annual rate: not rate / 4."""
    return (ONE + annual_rate) ** (Decimal(-quarter) / QUARTERS_PER_YEAR)


@exact
def discounted(
    flows: Sequence[Decimal],
    last_year: Sequence[Decimal],
    annual_rate: Decimal,
    growth: Decimal,
) -> Dcf:
    """Explicit quarters plus a perpetuity that repeats ``last_year``, growing yearly.

    Each quarter after the horizon is the same quarter a year earlier times (1 + g), so seasons
    survive. Its value at the end of the horizon is

        TV = (1 + g)(1 + r) / (r − g) × Σ last_year[k] / (1 + r)^(k / 4),  k = 1 to 4

    the quarterly form of FCFF_{N+1} / (r − g). With the whole year's flow in its last quarter
    it is exactly that formula, and a constant-growth stream gets the same value at any horizon.
    """
    finite(annual_rate, "dcf.annual_rate")
    finite(growth, "dcf.growth")
    if annual_rate <= 0:
        raise FinanceError("rate_not_positive", "dcf.annual_rate", f"{annual_rate} is not above 0")
    if growth <= -ONE:
        raise FinanceError("out_of_range", "dcf.growth", f"{growth} is at or below -100%")
    if annual_rate <= growth:
        raise FinanceError(
            "wacc_not_above_growth", "dcf.growth", f"needs {annual_rate} above {growth}"
        )
    if not flows:
        raise FinanceError("empty_horizon", "dcf.flows", "at least one quarter")
    if len(last_year) != QUARTERS_PER_YEAR:
        raise FinanceError("short_horizon", "dcf.last_year", "a terminal year has four quarters")
    for flow in (*flows, *last_year):
        finite(flow, "dcf.flows")

    present = sum(
        (flow * discount_factor(quarter, annual_rate) for quarter, flow in enumerate(flows, 1)),
        ZERO,
    )
    if sum(last_year, ZERO) <= 0:
        return Dcf(present, None, None, None, Ratio(None, NO_TERMINAL), NO_TERMINAL)
    year = sum(
        (flow * discount_factor(k, annual_rate) for k, flow in enumerate(last_year, 1)), ZERO
    )
    terminal = (ONE + growth) * (ONE + annual_rate) / (annual_rate - growth) * year
    present_terminal = terminal * discount_factor(len(flows), annual_rate)
    enterprise = present + present_terminal
    return Dcf(
        present, terminal, present_terminal, enterprise, ratio(present_terminal, enterprise, NO_EV)
    )


@exact
def with_exit_multiple(
    flows: Sequence[Decimal],
    last_year_ebitda: Sequence[Decimal],
    annual_rate: Decimal,
    multiple: Decimal,
) -> Dcf:
    """The same explicit quarters, with TV = EBITDA of the last year × multiple."""
    finite(annual_rate, "dcf.annual_rate")
    if annual_rate <= 0:
        raise FinanceError("rate_not_positive", "dcf.annual_rate", f"{annual_rate} is not above 0")
    if finite(multiple, "dcf.multiple") <= 0:
        raise FinanceError("multiple_not_positive", "dcf.multiple", f"{multiple} is not above 0")
    if len(last_year_ebitda) != QUARTERS_PER_YEAR:
        raise FinanceError("short_horizon", "dcf.last_year", "a terminal year has four quarters")
    present = sum(
        (flow * discount_factor(quarter, annual_rate) for quarter, flow in enumerate(flows, 1)),
        ZERO,
    )
    ebitda = sum(last_year_ebitda, ZERO)
    if ebitda <= 0:
        return Dcf(present, None, None, None, Ratio(None, NO_EBITDA), NO_EBITDA)
    terminal = ebitda * multiple
    present_terminal = terminal * discount_factor(len(flows), annual_rate)
    enterprise = present + present_terminal
    return Dcf(
        present, terminal, present_terminal, enterprise, ratio(present_terminal, enterprise, NO_EV)
    )


@exact
def implied_growth(
    terminal_value: Decimal, last_year: Sequence[Decimal], annual_rate: Decimal
) -> Decimal | None:
    """The g a Gordon perpetuity would need to reach this terminal value: a check on a multiple.

    From TV = (1 + g)(1 + r) / (r − g) × Y, with Y the last year discounted within its year.
    """
    year = sum(
        (flow * discount_factor(k, annual_rate) for k, flow in enumerate(last_year, 1)), ZERO
    )
    if year <= 0 or terminal_value <= 0:
        return None
    grown = (ONE + annual_rate) * year
    return (terminal_value * annual_rate - grown) / (terminal_value + grown)


@exact
def sensitivity(
    flows: Sequence[Decimal],
    last_year: Sequence[Decimal],
    rates: Sequence[Decimal],
    growths: Sequence[Decimal],
) -> tuple[tuple[Decimal | None, ...], ...]:
    """EV for each rate and growth. A cell with WACC at or below growth has no value at all."""
    return tuple(
        tuple(
            discounted(flows, last_year, rate, growth).enterprise_value if rate > growth else None
            for growth in growths
        )
        for rate in rates
    )


@exact
def weighted_value(values: Sequence[Decimal], weights: Sequence[Decimal]) -> Decimal:
    """Scenario weights are shares of a whole: they add up to exactly 1."""
    if len(values) != len(weights) or not values:
        raise FinanceError("weights", "scenarios", "one weight for each value")
    for weight in weights:
        share(weight, "scenarios.weight")
    if sum(weights, ZERO) != ONE:
        raise FinanceError("shares_sum", "scenarios.weight", "weights add up to exactly 100%")
    return sum(
        (finite(v, "scenarios.value") * w for v, w in zip(values, weights, strict=True)), ZERO
    )


@exact
def retained_share(diluted_shares: Decimal, new_shares: Decimal) -> Decimal:
    """Share of equity value left to today's holders after new shares at no consideration.

    A count of shares, never a price: price per share stays out of V1 to V3 (D-06), because it
    needs corporate actions and market data this project does not hold.
    """
    if finite(diluted_shares, "shares.diluted") <= 0:
        raise FinanceError("shares_not_positive", "shares.diluted", "a company has shares")
    at_least(new_shares, ZERO, "shares.new")
    return diluted_shares / (diluted_shares + new_shares)


def enterprise_value(path: StatementPath, capital: CapitalCost, growth: Decimal) -> Dcf:
    """FCFF at WACC. Transactions count in their quarter; the perpetuity repeats what recurs."""
    periods = path.periods
    if len(periods) < QUARTERS_PER_YEAR:
        raise FinanceError("short_horizon", "path.periods", "a terminal year has four quarters")
    return discounted(
        [period.free_cash.fcff for period in periods],
        [period.free_cash.fcff_recurring for period in periods[-QUARTERS_PER_YEAR:]],
        capital.wacc,
        growth,
    )


@dataclass(frozen=True, slots=True)
class Bridge:
    """EV and equity value are different outputs, joined by what ranks ahead of shareholders."""

    enterprise_value: Decimal | None
    debt: Decimal
    cash: Decimal
    other_senior_claims: Decimal
    non_operating_assets: Decimal
    equity_value: Decimal | None
    reason: str | None = None


@exact
def equity_bridge(dcf: Dcf, opening: Opening, other_senior_claims: Decimal = ZERO) -> Bridge:
    """Equity = EV − debt + cash − other senior claims + non-operating assets, at the base date.

    Leases, pensions, preferred stock and minorities enter as other senior claims. The restructuring
    provision does not: its payments are already in FCFF. Price per share stays out (D-06).
    """
    at_least(other_senior_claims, ZERO, "bridge.other_senior_claims")
    debt = opening.term_debt + opening.revolver
    equity = None
    if dcf.enterprise_value is not None:
        equity = (
            dcf.enterprise_value
            - debt
            + opening.cash
            - other_senior_claims
            + opening.non_operating_assets
        )
    return Bridge(
        dcf.enterprise_value,
        debt,
        opening.cash,
        other_senior_claims,
        opening.non_operating_assets,
        equity,
        dcf.reason,
    )
