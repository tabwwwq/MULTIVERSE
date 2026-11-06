"""Event accounting: each of the six decisions compiled into entries of the ledger.

A compiled plan is one realized path. Uncertain parameters arrive here as numbers, and a deal
either closes or it does not: scaling a deal by its probability would book a fraction of a
company, and such a path could not reconcile. Sampling them is the job of Stage 22.

Effects are read from the baseline and do not see one another: two decisions on one path add up.
The whitepaper holds the journal of each decision.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from multiverse_finance.exact import (
    ONE,
    QUARTERS_PER_YEAR,
    ZERO,
    FinanceError,
    at_least,
    between,
    exact,
    finite,
    share,
    whole,
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
)
from multiverse_finance.model import Baseline, Drivers
from multiverse_finance.schedules import ramp, shifted, spread

NO_REVENUE_RETURN = "No revenue return of R&D is assumed: none has been measured."


@dataclass(frozen=True, slots=True)
class Timing:
    """Quarters counted from the base date: the effective quarter is 1 or later."""

    effective_quarter: int
    lag_quarters: int = 0
    ramp_quarters: int = 0

    def __post_init__(self) -> None:
        whole(self.effective_quarter, 1, "timing.effective_quarter")
        whole(self.lag_quarters, 0, "timing.lag_quarters")
        whole(self.ramp_quarters, 0, "timing.ramp_quarters")

    @property
    def start(self) -> int:
        return self.effective_quarter + self.lag_quarters


@dataclass(frozen=True, slots=True)
class Funding:
    """Shares of a funding need. They add up to exactly 1, as in the contract."""

    cash: Decimal = ONE
    debt: Decimal = ZERO
    equity: Decimal = ZERO

    def __post_init__(self) -> None:
        total = (
            share(self.cash, "funding.cash")
            + share(self.debt, "funding.debt")
            + share(self.equity, "funding.equity")
        )
        if total != ONE:
            raise FinanceError("shares_sum", "funding", f"shares add up to {total}, not 1")


def _fund(
    decision: str,
    needs: Iterable[tuple[int, Decimal]],
    funding: Funding,
    rate: Decimal,
) -> list[Entry]:
    """New debt and equity on the first day of each quarter with a need; the rest is cash."""
    entries: list[Entry] = []
    for quarter, need in needs:
        entries.append(Borrow(quarter, decision, need * funding.debt, rate))
        entries.append(Issue(quarter, need * funding.equity))
    return entries


def _table(
    label: str, funding: Funding, uses: tuple[tuple[str, Decimal], ...], funded: Decimal
) -> SourcesUses:
    """The funding table of what falls inside the horizon."""
    sources = (
        ("cash on hand", funded * funding.cash),
        ("new debt", funded * funding.debt),
        ("new equity", funded * funding.equity),
    )
    return SourcesUses(label, sources, uses)


def _sold_like_baseline(
    quarter: int, segment: str, revenue: Decimal, drivers: Drivers
) -> list[Entry]:
    """Extra revenue with the COGS and SG&A of the baseline: no better margin is assumed."""
    return [
        Flow(quarter, Line.REVENUE, revenue, segment),
        Flow(quarter, Line.COGS, revenue * drivers.cogs_ratio),
        Flow(quarter, Line.SGA, revenue * drivers.sga_ratio),
    ]


def _split_cost(quarter: int, amount: Decimal, drivers: Drivers) -> list[Entry]:
    """A cost with no named line, shared between COGS and SG&A as in the baseline."""
    total = drivers.cogs_ratio + drivers.sga_ratio
    cogs = amount * drivers.cogs_ratio / total if total else amount
    return [Flow(quarter, Line.COGS, cogs), Flow(quarter, Line.SGA, amount - cogs)]


def _nonzero(entries: Iterable[Entry]) -> tuple[Entry, ...]:
    """Flows and financing of size 0 say nothing: a zero decision leaves an empty ledger."""
    return tuple(
        entry
        for entry in entries
        if not isinstance(entry, Flow | Charge | Payment | Capitalize | InService | Borrow | Issue)
        or entry.amount != 0
    )


@dataclass(frozen=True, slots=True)
class RndTerms:
    """The change is in money per quarter of full effect, from one of two magnitudes."""

    timing: Timing
    fraction_of_budget: Decimal | None = None
    points_of_revenue: Decimal | None = None
    capitalized_fraction: Decimal = ZERO
    amortization_quarters: int = 20
    adoption_delay_quarters: int = 0
    revenue_return: Decimal = ZERO
    """Revenue per unit of extra spending, after the delay. 0 unless someone has a reason."""
    funding: Funding = Funding()

    def __post_init__(self) -> None:
        if (self.fraction_of_budget is None) == (self.points_of_revenue is None):
            raise FinanceError("magnitude", "rnd.magnitude", "give exactly one unit of magnitude")
        if self.fraction_of_budget is not None:
            at_least(self.fraction_of_budget, -ONE, "rnd.fraction_of_budget")
        if self.points_of_revenue is not None:
            between(self.points_of_revenue, Decimal(-100), Decimal(100), "rnd.points_of_revenue")
        share(self.capitalized_fraction, "rnd.capitalized_fraction")
        whole(self.amortization_quarters, 1, "rnd.amortization_quarters")
        whole(self.adoption_delay_quarters, 0, "rnd.adoption_delay_quarters")
        at_least(self.revenue_return, ZERO, "rnd.revenue_return")


@exact
def rnd_change(baseline: Baseline, terms: RndTerms) -> Plan:
    """Spending moves now, any revenue moves later. Only extra spending can be capitalized."""
    horizon, timing = baseline.horizon, terms.timing
    shares = ramp(horizon, timing.start, timing.ramp_quarters)
    change = []
    for drivers, level in zip(baseline.quarters, shares, strict=True):
        if terms.fraction_of_budget is not None:
            full = terms.fraction_of_budget * drivers.rd_ratio * drivers.revenue
        else:
            points = terms.points_of_revenue if terms.points_of_revenue is not None else ZERO
            full = points / 100 * drivers.revenue
        change.append(full * level)

    entries: list[Entry] = []
    needs: list[tuple[int, Decimal]] = []
    for quarter, spending in enumerate(change, start=1):
        capitalized = max(spending, ZERO) * terms.capitalized_fraction
        entries.append(Flow(quarter, Line.RD_EXPENSE, spending - capitalized))
        entries.append(Capitalize(quarter, capitalized, terms.amortization_quarters))
        if spending > 0:
            needs.append((quarter, spending))
    delayed = shifted(change, terms.adoption_delay_quarters)
    for quarter, (drivers, spending) in enumerate(
        zip(baseline.quarters, delayed, strict=True), start=1
    ):
        if terms.revenue_return and spending:
            segment = drivers.segments[0][0]
            entries += _sold_like_baseline(
                quarter, segment, spending * terms.revenue_return, drivers
            )
    rate = baseline.policy.marginal_debt_rate
    entries += _fund("rnd_change", needs, terms.funding, rate)
    funded = sum((need for _, need in needs), ZERO)
    table = _table("rnd_change", terms.funding, (("extra R&D", funded),), funded)
    notes = () if terms.revenue_return else (NO_REVENUE_RETURN,)
    return Plan("rnd_change", _nonzero(entries), (table,) if funded else (), notes)


@dataclass(frozen=True, slots=True)
class WorkforceTerms:
    timing: Timing
    headcount_change: Decimal
    """Share of headcount: -0.15 is a cut of 15%."""
    payroll_to_revenue: Decimal
    one_off_cost_months: Decimal
    savings_realization: Decimal
    productivity_loss: Decimal = ZERO
    funding: Funding = Funding()

    def __post_init__(self) -> None:
        between(self.headcount_change, -ONE, ONE, "workforce.headcount_change")
        share(self.payroll_to_revenue, "workforce.payroll_to_revenue")
        at_least(self.one_off_cost_months, ZERO, "workforce.one_off_cost_months")
        share(self.savings_realization, "workforce.savings_realization")
        share(self.productivity_loss, "workforce.productivity_loss")


@exact
def workforce_restructure(baseline: Baseline, terms: WorkforceTerms) -> Plan:
    """The charge comes when the plan is committed, cash when people leave, savings over the ramp.

    A cut is a provision, charged at the effective quarter and paid over the ramp. Hiring has no
    provision: its cost is expensed as it is paid. Lost output during the ramp lowers revenue and
    saves no cost.
    """
    horizon, timing = baseline.horizon, terms.timing
    shares = ramp(horizon, timing.start, timing.ramp_quarters)
    entries: list[Entry] = []
    for quarter, (drivers, level) in enumerate(zip(baseline.quarters, shares, strict=True), 1):
        costs = drivers.cogs_ratio + drivers.rd_ratio + drivers.sga_ratio
        if terms.payroll_to_revenue > costs:
            raise FinanceError(
                "payroll_exceeds_costs",
                "workforce.payroll_to_revenue",
                f"above costs in Q{quarter}",
            )
        if level == 0:
            continue
        payroll = terms.payroll_to_revenue * drivers.revenue
        change = terms.headcount_change * payroll * terms.savings_realization * level
        entries += _split_payroll(quarter, change, drivers)
        lost = terms.productivity_loss * (ONE - level) * drivers.revenue
        if lost and terms.headcount_change:
            weights = _segment_shares(drivers)
            for (segment, _), weight in zip(drivers.segments, weights, strict=True):
                entries.append(Flow(quarter, Line.REVENUE, -lost * weight, segment))

    if timing.effective_quarter > horizon:
        return Plan("workforce_restructure", ())
    first = baseline.quarters[timing.effective_quarter - 1]
    yearly_payroll = terms.payroll_to_revenue * first.revenue * QUARTERS_PER_YEAR
    one_off = abs(terms.headcount_change) * yearly_payroll * terms.one_off_cost_months / 12

    paid = spread(one_off, timing.start, timing.ramp_quarters, horizon)
    needs = [(quarter, amount) for quarter, amount in enumerate(paid, 1) if amount]
    if terms.headcount_change < 0:
        entries.append(Charge(timing.effective_quarter, one_off))
        entries += [Payment(quarter, amount) for quarter, amount in needs]
    else:
        entries += [Flow(quarter, Line.ONE_OFF, amount) for quarter, amount in needs]
    rate = baseline.policy.marginal_debt_rate
    entries += _fund("workforce_restructure", needs, terms.funding, rate)
    funded = sum((need for _, need in needs), ZERO)
    table = _table(
        "workforce_restructure", terms.funding, (("one-off staff cost", funded),), funded
    )
    return Plan("workforce_restructure", _nonzero(entries), (table,) if funded else ())


def _split_payroll(quarter: int, amount: Decimal, drivers: Drivers) -> list[Entry]:
    """Payroll sits in all three cost lines, in the proportion of the baseline."""
    total = drivers.cogs_ratio + drivers.rd_ratio + drivers.sga_ratio
    if not total:
        return []
    return [
        Flow(quarter, Line.COGS, amount * drivers.cogs_ratio / total),
        Flow(quarter, Line.RD_EXPENSE, amount * drivers.rd_ratio / total),
        Flow(quarter, Line.SGA, amount * drivers.sga_ratio / total),
    ]


def _segment_shares(drivers: Drivers) -> tuple[Decimal, ...]:
    revenue = drivers.revenue
    if not revenue:
        return tuple(ZERO for _ in drivers.segments)
    return tuple(value / revenue for _, value in drivers.segments)


@dataclass(frozen=True, slots=True)
class AcquisitionTerms:
    timing: Timing
    price: Decimal
    target_revenue: Decimal
    """Per year, flat: the target's growth is not assumed."""
    target_ebitda_margin: Decimal
    deal_cost_fraction: Decimal
    integration_cost_fraction: Decimal
    cost_synergy_fraction: Decimal
    new_debt_rate: Decimal
    funding: Funding
    ppe_share: Decimal = ZERO
    intangibles_share: Decimal = ZERO
    intangibles_life_quarters: int = 40
    completed: bool = True
    synergy_delay_quarters: int = 0

    def __post_init__(self) -> None:
        at_least(self.price, ZERO, "acquisition.price")
        at_least(self.target_revenue, ZERO, "acquisition.target_revenue")
        between(self.target_ebitda_margin, -ONE, ONE, "acquisition.target_ebitda_margin")
        share(self.deal_cost_fraction, "acquisition.deal_cost_fraction")
        at_least(self.integration_cost_fraction, ZERO, "acquisition.integration_cost_fraction")
        at_least(self.cost_synergy_fraction, ZERO, "acquisition.cost_synergy_fraction")
        share(self.new_debt_rate, "acquisition.new_debt_rate")
        share(self.ppe_share, "acquisition.ppe_share")
        share(self.intangibles_share, "acquisition.intangibles_share")
        whole(self.intangibles_life_quarters, 1, "acquisition.intangibles_life_quarters")
        whole(self.synergy_delay_quarters, 0, "acquisition.synergy_delay_quarters")
        if self.funding.debt > 0 and self.price > 0 and self.new_debt_rate == 0:
            raise FinanceError(
                "rate_required", "acquisition.new_debt_rate", "new debt needs a rate above 0"
            )


@exact
def acquisition(baseline: Baseline, terms: AcquisitionTerms) -> Plan:
    """Price, deal costs, purchase allocation, integration and late synergies.

    The whole price is an outflow of FCFF however it is funded, so value can rise only through
    what the target earns. A deal that fails costs its deal costs and nothing else.
    """
    horizon, closing = baseline.horizon, terms.timing.start
    if closing > horizon:
        return Plan("acquisition", ())
    deal_costs = terms.price * terms.deal_cost_fraction
    entries: list[Entry] = [Flow(closing, Line.ONE_OFF, deal_costs)]
    if not terms.completed:
        costs_only = (("deal costs", deal_costs),)
        table = _table("acquisition (failed)", Funding(), costs_only, deal_costs)
        return Plan("acquisition", _nonzero(entries), (table,) if deal_costs else ())

    nwc_ratio = baseline.quarters[closing - 1].nwc_ratio
    entries.append(
        Purchase(
            closing,
            terms.price,
            ppe=terms.price * terms.ppe_share,
            trade_nwc=nwc_ratio * terms.target_revenue,
            intangibles=terms.price * terms.intangibles_share,
            intangibles_life_quarters=terms.intangibles_life_quarters,
        )
    )
    need = terms.price + deal_costs
    entries += _fund("acquisition", [(closing, need)], terms.funding, terms.new_debt_rate)

    revenue = terms.target_revenue / QUARTERS_PER_YEAR
    synergy_start = closing + terms.timing.ramp_quarters + terms.synergy_delay_quarters
    integration = spread(
        terms.price * terms.integration_cost_fraction, closing, terms.timing.ramp_quarters, horizon
    )
    for quarter in range(closing, horizon + 1):
        drivers = baseline.quarters[quarter - 1]
        entries.append(Flow(quarter, Line.REVENUE, revenue, "acquired"))
        entries += _split_cost(quarter, revenue * (ONE - terms.target_ebitda_margin), drivers)
        entries.append(Flow(quarter, Line.ONE_OFF, integration[quarter - 1]))
        if quarter >= synergy_start:
            entries += _split_cost(quarter, -revenue * terms.cost_synergy_fraction, drivers)
    uses = (("purchase price", terms.price), ("deal costs", deal_costs))
    table = _table("acquisition", terms.funding, uses, need)
    return Plan("acquisition", _nonzero(entries), (table,) if need else ())


@dataclass(frozen=True, slots=True)
class DivestitureTerms:
    timing: Timing
    revenue_fraction: Decimal
    unit_ebitda_margin: Decimal
    proceeds: Decimal
    separation_cost_fraction: Decimal
    stranded_cost_fraction: Decimal
    tax_rate_on_gain: Decimal
    debt_paydown: Decimal
    cash_retained: Decimal
    shareholder_distribution: Decimal

    def __post_init__(self) -> None:
        share(self.revenue_fraction, "divestiture.revenue_fraction")
        between(self.unit_ebitda_margin, -ONE, ONE, "divestiture.unit_ebitda_margin")
        at_least(self.proceeds, ZERO, "divestiture.proceeds")
        at_least(self.separation_cost_fraction, ZERO, "divestiture.separation_cost_fraction")
        share(self.stranded_cost_fraction, "divestiture.stranded_cost_fraction")
        share(self.tax_rate_on_gain, "divestiture.tax_rate_on_gain")
        total = (
            finite(self.debt_paydown, "divestiture.debt_paydown")
            + finite(self.cash_retained, "divestiture.cash_retained")
            + finite(self.shareholder_distribution, "divestiture.shareholder_distribution")
        )
        if total != ONE:
            raise FinanceError("shares_sum", "divestiture", f"proceeds add up to {total}, not 1")


@exact
def divestiture(baseline: Baseline, terms: DivestitureTerms) -> Plan:
    """The unit leaves on the first day with its share of book assets; overhead leaves slowly.

    The unit carried its share of SG&A. All of that stays at first and settles to the stranded
    fraction over the ramp, so EBITDA falls by the unit's EBITDA plus what stays stranded.
    """
    horizon, closing = baseline.horizon, terms.timing.start
    if closing > horizon:
        return Plan("divestiture", ())
    shares = ramp(horizon, closing, terms.timing.ramp_quarters)
    entries: list[Entry] = []
    for quarter in range(closing, horizon + 1):
        drivers = baseline.quarters[quarter - 1]
        unit_revenue = terms.revenue_fraction * drivers.revenue
        for segment, value in drivers.segments:
            amount = -terms.revenue_fraction * value
            entries.append(Flow(quarter, Line.REVENUE, amount, segment))
        unit_costs = unit_revenue * (ONE - terms.unit_ebitda_margin)
        overhead = min(terms.revenue_fraction * drivers.sga_ratio * drivers.revenue, unit_costs)
        stranded = ONE - (ONE - terms.stranded_cost_fraction) * shares[quarter - 1]
        entries.append(Flow(quarter, Line.COGS, overhead - unit_costs))
        entries.append(Flow(quarter, Line.SGA, -overhead * (ONE - stranded)))
    yearly = terms.revenue_fraction * baseline.quarters[closing - 1].revenue * QUARTERS_PER_YEAR
    entries.append(
        Sale(
            closing,
            terms.revenue_fraction,
            terms.proceeds,
            yearly * terms.separation_cost_fraction,
            terms.tax_rate_on_gain,
            terms.debt_paydown,
            terms.shareholder_distribution,
        )
    )
    return Plan("divestiture", _nonzero(entries))


@dataclass(frozen=True, slots=True)
class CapexTerms:
    timing: Timing
    """The lag is construction, the ramp is how long utilization takes to reach its level."""
    investment: Decimal
    capacity_increase: Decimal
    useful_life_years: int
    utilization: Decimal
    new_debt_rate: Decimal
    funding: Funding

    def __post_init__(self) -> None:
        at_least(self.investment, ZERO, "capex.investment")
        at_least(self.capacity_increase, ZERO, "capex.capacity_increase")
        whole(self.useful_life_years, 1, "capex.useful_life_years")
        share(self.utilization, "capex.utilization")
        share(self.new_debt_rate, "capex.new_debt_rate")
        if self.funding.debt > 0 and self.investment > 0 and self.new_debt_rate == 0:
            raise FinanceError(
                "rate_required", "capex.new_debt_rate", "new debt needs a rate above 0"
            )


@exact
def capex_expansion(baseline: Baseline, terms: CapexTerms) -> Plan:
    """Cash during construction, depreciation from use, revenue only as far as capacity is used."""
    horizon, timing = baseline.horizon, terms.timing
    outlay = spread(terms.investment, timing.effective_quarter, timing.lag_quarters, horizon)
    entries: list[Entry] = []
    needs = [(quarter, amount) for quarter, amount in enumerate(outlay, 1) if amount]
    entries += [Flow(quarter, Line.CONSTRUCTION, amount) for quarter, amount in needs]
    entries += _fund("capex_expansion", needs, terms.funding, terms.new_debt_rate)

    ready = timing.start
    if ready <= horizon:
        life = terms.useful_life_years * QUARTERS_PER_YEAR
        entries.append(InService(ready, terms.investment, life))
        levels = ramp(horizon, ready, timing.ramp_quarters)
        for quarter, (drivers, level) in enumerate(zip(baseline.quarters, levels, strict=True), 1):
            revenue = drivers.revenue * terms.capacity_increase * terms.utilization * level
            if revenue:
                entries += _sold_like_baseline(quarter, "new_capacity", revenue, drivers)
    funded = sum((need for _, need in needs), ZERO)
    table = _table("capex_expansion", terms.funding, (("investment", funded),), funded)
    return Plan("capex_expansion", _nonzero(entries), (table,) if funded else ())


@dataclass(frozen=True, slots=True)
class RefinanceTerms:
    timing: Timing
    amount: Decimal
    new_rate: Decimal
    new_maturity_years: int
    fee_fraction: Decimal

    def __post_init__(self) -> None:
        at_least(self.amount, ZERO, "refinance.amount")
        share(self.new_rate, "refinance.new_rate")
        whole(self.new_maturity_years, 1, "refinance.new_maturity_years")
        share(self.fee_fraction, "refinance.fee_fraction")


@exact
def debt_refinance(baseline: Baseline, terms: RefinanceTerms) -> Plan:
    """New debt replaces old; only the rate, the maturity and the fees change.

    Fees are expensed when paid: a simplification of amortizing issuance costs (the whitepaper
    says what it moves). The rate saved is the rate of the tranches actually retired.
    """
    if terms.amount > baseline.opening.term_debt:
        raise FinanceError("impossible_debt", "refinance.amount", "more than the term debt")
    horizon, timing = baseline.horizon, terms.timing
    parts = spread(terms.amount, timing.start, timing.ramp_quarters, horizon)
    maturity = timing.start + terms.new_maturity_years * QUARTERS_PER_YEAR
    entries: list[Entry] = []
    replaced = ZERO
    for quarter, part in enumerate(parts, 1):
        if part:
            entries.append(Retire(quarter, part, keep="refinance"))
            entries.append(Borrow(quarter, "refinance", part, terms.new_rate, maturity))
            entries.append(Flow(quarter, Line.FINANCING_FEE, part * terms.fee_fraction))
            replaced += part
    fees = replaced * terms.fee_fraction
    table = SourcesUses(
        "debt_refinance",
        (("new debt", replaced), ("cash on hand", fees)),
        (("old debt repaid", replaced), ("fees", fees)),
    )
    return Plan("debt_refinance", _nonzero(entries), (table,) if replaced else ())
