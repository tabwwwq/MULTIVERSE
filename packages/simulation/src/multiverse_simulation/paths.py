"""From a case and one draw of shocks to the finance baseline of that path.

Revenue moves by symmetric growth over the same quarter a year earlier, so it keeps its seasons
and cannot turn negative: a = b (2 + s) / (2 − s). Hard bounds keep growth and margin inside what
the definitions allow; each quarter that meets one is counted.
"""

from dataclasses import dataclass
from decimal import Decimal

from multiverse_contracts.simulation import CaseOpening, CasePolicy, SimulationCase
from multiverse_finance.model import Baseline, Drivers, Opening, Policy, Tranche
from multiverse_finance.valuation import CapitalCost
from multiverse_simulation.shocks import PathShocks

MAX_GROWTH = 1.9
MIN_MARGIN = -1.0
MIN_CASH_COST = 0.01
"""A company always pays something: costs other than R&D stay above this share of revenue."""
SEGMENT = "total"


def _opening(opening: CaseOpening) -> Opening:
    return Opening(
        cash=Decimal(opening.cash),
        trade_nwc=Decimal(opening.trade_nwc),
        ppe=Decimal(opening.ppe),
        intangibles=Decimal(opening.intangibles),
        goodwill=Decimal(opening.goodwill),
        non_operating_assets=Decimal(opening.non_operating_assets),
        tranches=tuple(
            Tranche(
                t.name,
                Decimal(t.principal),
                Decimal(t.annual_rate),
                t.maturity_quarter,
                t.floating,
            )
            for t in opening.tranches
        ),
        trailing_ebitda=tuple(Decimal(value) for value in opening.trailing_ebitda),
        trailing_interest=tuple(Decimal(value) for value in opening.trailing_interest),
    )


def _policy(policy: CasePolicy) -> Policy:
    return Policy(
        tax_rate=Decimal(policy.tax_rate),
        depreciation_rate=Decimal(policy.depreciation_rate),
        amortization_rate=Decimal(policy.amortization_rate),
        cash_yield=Decimal(policy.cash_yield),
        minimum_cash=Decimal(policy.minimum_cash),
        revolver_limit=Decimal(policy.revolver_limit),
        revolver_rate=Decimal(policy.revolver_rate),
        marginal_debt_rate=Decimal(policy.marginal_debt_rate),
        dividend_payout=Decimal(policy.dividend_payout),
        max_leverage=Decimal(policy.max_leverage),
        min_interest_cover=Decimal(policy.min_interest_cover),
    )


@dataclass(frozen=True)
class Prepared:
    """What every path of a case shares, parsed once."""

    case: SimulationCase
    opening: Opening
    policy: Policy
    capital: CapitalCost
    growth: Decimal
    last_year: tuple[float, ...]

    @classmethod
    def of(cls, case: SimulationCase) -> "Prepared":
        capital = case.capital
        return cls(
            case,
            _opening(case.opening),
            _policy(case.policy),
            CapitalCost(
                Decimal(capital.risk_free),
                Decimal(capital.equity_risk_premium),
                Decimal(capital.beta),
                Decimal(capital.pre_tax_cost_of_debt),
                Decimal(capital.tax_rate),
                Decimal(capital.debt_weight),
            ),
            Decimal(capital.terminal_growth),
            tuple(float(value) for value in case.drivers.last_year_revenue),
        )


def _ratio(value: float) -> Decimal:
    return Decimal(f"{value:.6f}")


def path_baseline(prepared: Prepared, shocks: PathShocks) -> tuple[Baseline, int]:
    """The baseline of one path, and how many of its quarters met a hard bound."""
    case = prepared.case
    drivers, central = case.drivers, case.central
    revenue = list(prepared.last_year)
    quarters: list[Drivers] = []
    clipped = 0
    capex, nwc = _ratio(drivers.capex_ratio), _ratio(drivers.nwc_ratio)
    rd = _ratio(drivers.rd_ratio)
    top_margin = 1.0 - drivers.rd_ratio - MIN_CASH_COST
    for quarter in range(case.horizon):
        wanted = central.growth[quarter] + float(shocks.growth[quarter])
        growth = min(max(wanted, -MAX_GROWTH), MAX_GROWTH)
        margin_wanted = central.margin[quarter] + float(shocks.margin[quarter])
        margin = min(max(margin_wanted, MIN_MARGIN), top_margin)
        clipped += int(growth != wanted) + int(margin != margin_wanted)
        level = revenue[quarter] * (2.0 + growth) / (2.0 - growth)
        revenue.append(level)
        rest = 1.0 - margin - drivers.rd_ratio
        cogs = rest * drivers.cogs_share
        quarters.append(
            Drivers(
                segments=((SEGMENT, Decimal(f"{level:.2f}")),),
                cogs_ratio=_ratio(cogs),
                rd_ratio=rd,
                sga_ratio=_ratio(rest - cogs),
                capex_ratio=capex,
                nwc_ratio=nwc,
                rate_shift=_ratio(float(shocks.rate_shift[quarter])),
            )
        )
    baseline = Baseline(
        case.currency, case.balance_date, prepared.opening, prepared.policy, tuple(quarters)
    )
    return baseline, clipped
