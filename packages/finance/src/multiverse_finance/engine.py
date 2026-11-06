"""The statement engine: quarter after quarter, from the baseline and the entries of decisions.

Order inside a quarter (the whitepaper explains each choice):

1. First day: sales, purchases, maturities, planned debt and equity, assets placed in service.
2. Income statement. Interest runs on term debt after the first day and on the opening revolver
   and cash, so nothing in a quarter depends on its own closing balance: no circular reference.
3. Cash flow, then the liquidity waterfall: dividends only from cash above the minimum, surplus
   repays first the shortfall and then the revolver, a deficit draws the revolver up to its limit.
   What no lender covers becomes a funding shortfall. Cash itself never goes negative.
4. Every quarter of every path is reconciled before it leaves ``project``.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal

from multiverse_finance.checks import assert_reconciled
from multiverse_finance.exact import (
    EPSILON,
    ONE,
    QUARTERS_PER_YEAR,
    ZERO,
    FinanceError,
    Ratio,
    exact,
    ratio,
)
from multiverse_finance.ledger import (
    Borrow,
    Capitalize,
    Charge,
    Entry,
    Flow,
    InService,
    Issue,
    Line,
    Payment,
    Plan,
    Purchase,
    Retire,
    Sale,
    SourcesUses,
    check_entry,
)
from multiverse_finance.model import Baseline, Drivers, Opening, Policy, Tranche
from multiverse_finance.statements import (
    Balance,
    CashFlow,
    Credit,
    FreeCash,
    Income,
    Period,
    StatementPath,
)

TTM_QUARTERS = 4
NO_HISTORY = "undefined: fewer than four quarters of history"
NO_EBITDA = "undefined: EBITDA <= 0"
NO_INTEREST = "undefined: no interest expense"


@dataclass(slots=True)
class _Vintage:
    """An asset depreciated in a straight line, from the quarter it is placed in service."""

    intangible: bool
    remaining: Decimal
    per_quarter: Decimal

    def charge(self) -> Decimal:
        amount = min(self.per_quarter, self.remaining)
        self.remaining -= amount
        return amount


@dataclass(slots=True)
class _State:
    """Closing balances of the last quarter. Private: only ``project`` ever changes them."""

    cash: Decimal
    trade_nwc: Decimal
    provision: Decimal
    pool_ppe: Decimal
    construction: Decimal
    pool_intangibles: Decimal
    goodwill: Decimal
    non_operating_assets: Decimal
    tranches: dict[str, Tranche]
    revolver: Decimal
    shortfall: Decimal
    equity: Decimal
    tax_losses: Decimal
    unlevered_tax_losses: Decimal
    ebitda: list[Decimal]
    interest: list[Decimal]
    vintages: list[_Vintage] = field(default_factory=list)

    @classmethod
    def opening(cls, opening: Opening) -> "_State":
        return cls(
            cash=opening.cash,
            trade_nwc=opening.trade_nwc,
            provision=opening.provision,
            pool_ppe=opening.ppe,
            construction=ZERO,
            pool_intangibles=opening.intangibles,
            goodwill=opening.goodwill,
            non_operating_assets=opening.non_operating_assets,
            tranches={tranche.name: tranche for tranche in opening.tranches},
            revolver=opening.revolver,
            shortfall=ZERO,
            equity=opening.equity,
            tax_losses=opening.tax_losses,
            unlevered_tax_losses=opening.tax_losses,
            ebitda=list(opening.trailing_ebitda),
            interest=list(opening.trailing_interest),
        )

    @property
    def term_debt(self) -> Decimal:
        return sum((tranche.principal for tranche in self.tranches.values()), ZERO)

    def book(self, intangible: bool) -> Decimal:
        return sum((v.remaining for v in self.vintages if v.intangible is intangible), ZERO)

    def repay(self, amount: Decimal, keep: str | None = None) -> Decimal:
        """Repay term debt, oldest tranche first; returns what was repaid."""
        left = amount
        for name, tranche in self.tranches.items():
            if name == keep:
                continue
            part = min(left, tranche.principal)
            self.tranches[name] = replace(tranche, principal=tranche.principal - part)
            left -= part
        return amount - left

    def borrow(self, loan: Borrow) -> None:
        """A second loan in one tranche blends the rate and keeps the earlier maturity."""
        current = self.tranches.get(loan.tranche)
        if current is None:
            self.tranches[loan.tranche] = Tranche(
                loan.tranche, loan.amount, loan.annual_rate, loan.maturity_quarter
            )
            return
        principal = current.principal + loan.amount
        interest = current.principal * current.annual_rate + loan.amount * loan.annual_rate
        due = [q for q in (current.maturity_quarter, loan.maturity_quarter) if q is not None]
        self.tranches[loan.tranche] = replace(
            current,
            principal=principal,
            annual_rate=interest / principal if principal else loan.annual_rate,
            maturity_quarter=min(due, default=None),
        )


@dataclass(slots=True)
class _FirstDay:
    """What happened on the first day of a quarter."""

    purchases: Decimal = ZERO
    proceeds: Decimal = ZERO
    separation: Decimal = ZERO
    gain: Decimal = ZERO
    disposal_tax: Decimal = ZERO
    nwc_bought: Decimal = ZERO
    nwc_sold: Decimal = ZERO
    drawn: Decimal = ZERO
    repaid: Decimal = ZERO
    issued: Decimal = ZERO
    sales: list[tuple[Sale, Decimal]] = field(default_factory=list)


def _sell(state: _State, sale: Sale, day: _FirstDay) -> None:
    """Take a share of every operating book value out; the gain is proceeds over book value."""
    kept = ONE - sale.fraction
    nwc = sale.fraction * state.trade_nwc
    book = nwc + sale.fraction * (
        state.pool_ppe
        + state.construction
        + state.pool_intangibles
        + state.goodwill
        + state.book(True)
        + state.book(False)
    )
    state.trade_nwc -= nwc
    state.pool_ppe *= kept
    state.construction *= kept
    state.pool_intangibles *= kept
    state.goodwill *= kept
    for vintage in state.vintages:
        vintage.remaining *= kept
        vintage.per_quarter *= kept
    gain = sale.proceeds - book
    tax = max(gain, ZERO) * sale.tax_rate_on_gain
    day.proceeds += sale.proceeds
    day.separation += sale.separation_cost
    day.gain += gain
    day.disposal_tax += tax
    day.nwc_sold += nwc
    day.sales.append((sale, tax))


def _buy(state: _State, purchase: Purchase, day: _FirstDay) -> None:
    state.pool_ppe += purchase.ppe
    state.trade_nwc += purchase.trade_nwc
    state.goodwill += purchase.goodwill
    state.vintages.append(
        _Vintage(
            True,
            purchase.intangibles,
            purchase.intangibles / purchase.intangibles_life_quarters,
        )
    )
    day.purchases += purchase.price
    day.nwc_bought += purchase.trade_nwc


def _mature(state: _State, policy: Policy, quarter: int, day: _FirstDay) -> None:
    """A tranche due this quarter rolls at the marginal rate, or is repaid if lenders are shut."""
    for name, tranche in list(state.tranches.items()):
        if tranche.maturity_quarter != quarter:
            continue
        day.repaid += tranche.principal
        if policy.can_refinance:
            day.drawn += tranche.principal
            state.tranches[name] = replace(
                tranche, annual_rate=policy.marginal_debt_rate, maturity_quarter=None
            )
        else:
            state.tranches[name] = replace(tranche, principal=ZERO, maturity_quarter=None)


def _first_day(state: _State, policy: Policy, quarter: int, entries: list[Entry]) -> _FirstDay:
    day = _FirstDay()
    for entry in entries:
        if isinstance(entry, Sale):
            _sell(state, entry, day)
    for entry in entries:
        if isinstance(entry, Purchase):
            _buy(state, entry, day)
    _mature(state, policy, quarter, day)
    for entry in entries:
        if isinstance(entry, Retire):
            repaid = state.repay(entry.amount, keep=entry.keep)
            if entry.amount - repaid > EPSILON:
                raise FinanceError(
                    "impossible_debt", "retire.amount", f"more than the debt left in Q{quarter}"
                )
            day.repaid += repaid
    for entry in entries:
        if isinstance(entry, Borrow):
            state.borrow(entry)
            day.drawn += entry.amount
        elif isinstance(entry, Issue):
            day.issued += entry.amount
        elif isinstance(entry, Flow) and entry.line is Line.CONSTRUCTION:
            state.construction += entry.amount
        elif isinstance(entry, Capitalize):
            state.vintages.append(_Vintage(True, entry.amount, entry.amount / entry.life_quarters))
    for entry in entries:
        if isinstance(entry, InService):
            moved = min(entry.amount, state.construction)
            state.construction -= moved
            state.vintages.append(_Vintage(False, moved, moved / entry.life_quarters))
    return day


def _segments(drivers: Drivers, entries: list[Entry]) -> tuple[tuple[str, Decimal], ...]:
    """Baseline segments in order, then new ones; a new segment with nothing in it is left out."""
    revenue = dict(drivers.segments)
    added: dict[str, Decimal] = {}
    for entry in entries:
        if isinstance(entry, Flow) and entry.line is Line.REVENUE and entry.segment is not None:
            if entry.segment in revenue:
                revenue[entry.segment] += entry.amount
            else:
                added[entry.segment] = added.get(entry.segment, ZERO) + entry.amount
    revenue.update({name: value for name, value in added.items() if value != 0})
    return tuple(revenue.items())


def _tax(profit: Decimal, losses: Decimal, rate: Decimal) -> tuple[Decimal, Decimal]:
    """Tax and the losses left. A loss earns no refund: it is carried forward without limit."""
    if profit <= 0:
        return ZERO, losses - profit
    used = min(losses, profit)
    return (profit - used) * rate, losses - used


def _depreciate(state: _State, policy: Policy) -> tuple[Decimal, Decimal]:
    """Pools decline by their rate; vintages run in a straight line. Capex joins after this."""
    depreciation = state.pool_ppe * policy.depreciation_rate / QUARTERS_PER_YEAR
    amortization = state.pool_intangibles * policy.amortization_rate / QUARTERS_PER_YEAR
    state.pool_ppe -= depreciation
    state.pool_intangibles -= amortization
    for vintage in state.vintages:
        if vintage.intangible:
            amortization += vintage.charge()
        else:
            depreciation += vintage.charge()
    return depreciation, amortization


def _liquidity(state: _State, policy: Policy, cash: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Cash after the waterfall, with the net change of the revolver and of the shortfall."""
    surplus = cash - policy.minimum_cash
    if surplus >= 0:
        to_shortfall = min(surplus, state.shortfall)
        to_revolver = min(surplus - to_shortfall, state.revolver)
        state.shortfall -= to_shortfall
        state.revolver -= to_revolver
        return cash - to_shortfall - to_revolver, -to_revolver, -to_shortfall
    drawn = min(-surplus, max(policy.revolver_limit - state.revolver, ZERO))
    state.revolver += drawn
    gap = max(-(cash + drawn), ZERO)
    state.shortfall += gap
    return cash + drawn + gap, drawn, gap


def _credit(state: _State, policy: Policy, net_debt: Decimal) -> tuple[Credit, tuple[str, ...]]:
    """Ratios on the last four quarters, and the covenants they break.

    Net debt above zero with EBITDA at or below zero breaks a leverage covenant, though the
    ratio itself stays undefined.
    """
    if len(state.ebitda) < TTM_QUARTERS or len(state.interest) < TTM_QUARTERS:
        none = Ratio(None, NO_HISTORY)
        return Credit(None, net_debt, none, none), ()
    ttm = sum(state.ebitda[-TTM_QUARTERS:], ZERO)
    interest = sum(state.interest[-TTM_QUARTERS:], ZERO)
    leverage = ratio(net_debt, ttm, NO_EBITDA)
    cover = ratio(ttm, interest, NO_INTEREST)
    alerts = []
    limit = policy.max_leverage
    if limit is not None and net_debt > 0 and (leverage.value is None or leverage.value > limit):
        alerts.append("leverage_breach")
    floor = policy.min_interest_cover
    if floor is not None and cover.value is not None and cover.value < floor:
        alerts.append("interest_cover_breach")
    return Credit(ttm, net_debt, leverage, cover), tuple(alerts)


def _book(
    baseline: Baseline, drivers: Drivers, quarter: int, entries: list[Entry], state: _State
) -> tuple[Period, list[SourcesUses]]:
    policy = baseline.policy
    cash_open, trade_open, provision_open = state.cash, state.trade_nwc, state.provision
    floating_open = state.revolver + state.shortfall

    day = _first_day(state, policy, quarter, entries)

    # Income statement.
    flows: dict[Line, Decimal] = defaultdict(lambda: ZERO)
    charged = paid = capitalized = ZERO
    for entry in entries:
        if isinstance(entry, Flow):
            flows[entry.line] += entry.amount
        elif isinstance(entry, Charge):
            charged += entry.amount
        elif isinstance(entry, Payment):
            paid += entry.amount
        elif isinstance(entry, Capitalize):
            capitalized += entry.amount
    segments = _segments(drivers, entries)
    revenue = sum((value for _, value in segments), ZERO)
    cogs = drivers.cogs_ratio * drivers.revenue + flows[Line.COGS]
    rd_expense = drivers.rd_ratio * drivers.revenue + flows[Line.RD_EXPENSE]
    sga = drivers.sga_ratio * drivers.revenue + flows[Line.SGA]
    for name, value in (("revenue", revenue), ("cogs", cogs), ("rd", rd_expense), ("sga", sga)):
        if value < -EPSILON:
            raise FinanceError("negative_line", f"Q{quarter}.{name}", f"{value} is below zero")
    one_off_paid = flows[Line.ONE_OFF] + day.separation
    one_off = one_off_paid + charged
    gross_profit = revenue - cogs
    ebitda = gross_profit - rd_expense - sga - one_off
    depreciation, amortization = _depreciate(state, policy)
    d_and_a = depreciation + amortization
    ebit = ebitda - d_and_a
    interest_expense = (
        sum((t.principal * t.annual_rate for t in state.tranches.values()), ZERO)
        + floating_open * policy.revolver_rate
    ) / QUARTERS_PER_YEAR
    interest_income = cash_open * policy.cash_yield / QUARTERS_PER_YEAR
    fees = flows[Line.FINANCING_FEE]
    pre_tax_income = ebit - interest_expense + interest_income - fees
    ordinary_tax, state.tax_losses = _tax(pre_tax_income, state.tax_losses, policy.tax_rate)
    tax_on_ebit, state.unlevered_tax_losses = _tax(
        ebit, state.unlevered_tax_losses, policy.tax_rate
    )
    net_income = pre_tax_income + day.gain - ordinary_tax - day.disposal_tax

    # Cash flow before financing.
    state.provision = provision_open + charged - paid
    if state.provision < -EPSILON:
        raise FinanceError("provision_overdrawn", f"Q{quarter}", "paid more than was provided")
    state.trade_nwc = drivers.nwc_ratio * revenue * QUARTERS_PER_YEAR
    delta_trade = state.trade_nwc - trade_open - day.nwc_bought + day.nwc_sold
    delta_nwc = delta_trade - (state.provision - provision_open)
    cfo = net_income + d_and_a - day.gain - delta_nwc
    pool_capex = drivers.capex_ratio * revenue
    state.pool_ppe += pool_capex
    construction = flows[Line.CONSTRUCTION]
    capex = pool_capex + construction + capitalized
    cfi = day.proceeds - capex - day.purchases

    # What the sale leaves after tax and separation goes where the decision says.
    tables: list[SourcesUses] = []
    paid_down = distributions = ZERO
    for sale, tax in day.sales:
        net = sale.proceeds - tax - sale.separation_cost
        wanted = max(net, ZERO) * sale.paydown_share
        repaid = state.repay(wanted)
        given = max(net, ZERO) * sale.distribution_share
        paid_down += repaid
        distributions += given
        if sale.fraction or sale.proceeds:
            tables.append(
                SourcesUses(
                    "divestiture",
                    (("sale proceeds", sale.proceeds), ("cash on hand", max(-net, ZERO))),
                    (
                        ("tax on the gain", tax),
                        ("separation cost", sale.separation_cost),
                        ("debt paid down", repaid),
                        ("distribution to shareholders", given),
                        ("cash retained", max(net, ZERO) - repaid - given),
                    ),
                )
            )

    # Liquidity.
    before = cash_open + cfo + cfi + day.drawn - day.repaid - paid_down + day.issued - distributions
    room = max(before - policy.minimum_cash, ZERO)
    dividends = min(policy.dividend_payout * max(net_income, ZERO), room)
    state.cash, revolver_net, shortfall_net = _liquidity(state, policy, before - dividends)
    state.equity += net_income + day.issued - dividends - distributions

    debt_repaid = day.repaid + paid_down
    net_borrowing = day.drawn - debt_repaid + revolver_net + shortfall_net
    cff = net_borrowing + day.issued - dividends - distributions
    cash_flow = CashFlow(
        delta_nwc=delta_nwc,
        cfo=cfo,
        capex=capex,
        acquisitions=day.purchases,
        disposal_proceeds=day.proceeds,
        cfi=cfi,
        debt_drawn=day.drawn,
        debt_repaid=debt_repaid,
        revolver_net=revolver_net,
        shortfall_net=shortfall_net,
        equity_issued=day.issued,
        dividends=dividends,
        distributions=distributions,
        cff=cff,
        net_change=state.cash - cash_open,
    )
    income = Income(
        segments=segments,
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        rd_expense=rd_expense,
        sga=sga,
        one_off=one_off,
        ebitda=ebitda,
        adjusted_ebitda=ebitda + one_off,
        depreciation=depreciation,
        amortization=amortization,
        ebit=ebit,
        interest_expense=interest_expense,
        interest_income=interest_income,
        financing_fees=fees,
        disposal_gain=day.gain,
        pre_tax_income=pre_tax_income,
        ordinary_tax=ordinary_tax,
        disposal_tax=day.disposal_tax,
        net_income=net_income,
    )
    balance = Balance(
        cash=state.cash,
        trade_nwc=state.trade_nwc,
        ppe=state.pool_ppe + state.construction + state.book(False),
        intangibles=state.pool_intangibles + state.book(True),
        goodwill=state.goodwill,
        non_operating_assets=state.non_operating_assets,
        provision=state.provision,
        term_debt=state.term_debt,
        revolver=state.revolver,
        shortfall=state.shortfall,
        equity=state.equity,
    )

    fcff_operating = ebit - tax_on_ebit + d_and_a - capex - delta_nwc
    transactions = day.proceeds - day.disposal_tax - day.purchases
    free_cash = FreeCash(
        tax_on_ebit=tax_on_ebit,
        fcff_operating=fcff_operating,
        transactions=transactions,
        fcff=fcff_operating + transactions,
        fcff_recurring=(
            fcff_operating + (one_off_paid + paid) * (ONE - policy.tax_rate) + construction
        ),
        fcf_simple=cfo - capex,
        tax_shield=tax_on_ebit - ordinary_tax,
        net_borrowing=net_borrowing,
        fcfe=cfo - capex - day.purchases + day.proceeds + net_borrowing,
    )

    state.ebitda.append(ebitda)
    state.interest.append(interest_expense)
    credit, breaches = _credit(state, policy, balance.net_debt)
    alerts = list(breaches)
    if state.cash < policy.minimum_cash:
        alerts.append("below_minimum_cash")
    if state.shortfall > 0:
        alerts.append("funding_shortfall")
    period = Period(
        quarter=quarter,
        income=income,
        cash_flow=cash_flow,
        balance=balance,
        free_cash=free_cash,
        credit=credit,
        tax_losses=state.tax_losses,
        alerts=tuple(alerts),
    )
    return period, tables


@exact
def project(baseline: Baseline, plans: Sequence[Plan] = ()) -> StatementPath:
    """Book the baseline and the decisions into one path of reconciled statements."""
    entries: dict[int, list[Entry]] = defaultdict(list)
    for plan in plans:
        for entry in plan.entries:
            check_entry(entry, baseline.horizon)
            entries[entry.quarter].append(entry)

    state = _State.opening(baseline.opening)
    funding = [table for plan in plans for table in plan.funding]
    periods = []
    for quarter, drivers in enumerate(baseline.quarters, start=1):
        period, tables = _book(baseline, drivers, quarter, entries[quarter], state)
        periods.append(period)
        funding.extend(tables)

    path = StatementPath(baseline.currency, baseline.base_date, tuple(periods), tuple(funding))
    assert_reconciled(path, baseline)
    return path
