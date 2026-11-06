"""An invented company for tests and the whitepaper. SYNTHETIC: no number here is observed."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from multiverse_finance.exact import exact
from multiverse_finance.interventions import (
    AcquisitionTerms,
    CapexTerms,
    DivestitureTerms,
    Funding,
    RefinanceTerms,
    RndTerms,
    Timing,
    WorkforceTerms,
    acquisition,
    capex_expansion,
    debt_refinance,
    divestiture,
    rnd_change,
    workforce_restructure,
)
from multiverse_finance.ledger import Plan
from multiverse_finance.model import CURRENCY, Baseline, Drivers, Opening, Policy, Tranche
from multiverse_finance.valuation import CapitalCost

SYNTHETIC = True


@exact
def illustrative_baseline(horizon: int = 12, unit: Decimal = Decimal(1)) -> Baseline:
    """Two segments, 2% growth a quarter, a loan due in quarter 8.

    Amounts read as millions; ``unit`` of 1000000 gives them in dollars, as the decisions of the
    contract are.
    """
    quarters = tuple(
        Drivers(
            segments=(
                ("products", 600 * unit * Decimal("1.02") ** quarter),
                ("services", 400 * unit * Decimal("1.02") ** quarter),
            ),
            cogs_ratio=Decimal("0.55"),
            rd_ratio=Decimal("0.08"),
            sga_ratio=Decimal("0.17"),
            capex_ratio=Decimal("0.05"),
            nwc_ratio=Decimal("0.10"),
        )
        for quarter in range(1, horizon + 1)
    )
    opening = Opening(
        cash=500 * unit,
        trade_nwc=400 * unit,
        ppe=2000 * unit,
        intangibles=300 * unit,
        goodwill=700 * unit,
        non_operating_assets=100 * unit,
        tranches=(
            Tranche("senior_notes", 1000 * unit, Decimal("0.05"), maturity_quarter=8),
            Tranche("term_loan", 500 * unit, Decimal("0.06"), floating=True),
        ),
        trailing_ebitda=(190 * unit, 195 * unit, 200 * unit),
        trailing_interest=(20 * unit, 20 * unit, 20 * unit),
    )
    policy = Policy(
        tax_rate=Decimal("0.25"),
        depreciation_rate=Decimal("0.10"),
        amortization_rate=Decimal("0.20"),
        cash_yield=Decimal("0.02"),
        minimum_cash=100 * unit,
        revolver_limit=300 * unit,
        revolver_rate=Decimal("0.07"),
        marginal_debt_rate=Decimal("0.065"),
        dividend_payout=Decimal("0.30"),
        max_leverage=Decimal("3.5"),
        min_interest_cover=Decimal("3"),
    )
    return Baseline(CURRENCY, date(2026, 6, 30), opening, policy, quarters)


def illustrative_decisions(baseline: Baseline) -> dict[str, Plan]:
    """One decision of each type, as the whitepaper books them. Invented, like the company."""
    deal = AcquisitionTerms(
        timing=Timing(2, lag_quarters=2, ramp_quarters=8),
        price=Decimal(1500),
        target_revenue=Decimal(800),
        target_ebitda_margin=Decimal("0.2"),
        deal_cost_fraction=Decimal("0.02"),
        integration_cost_fraction=Decimal("0.05"),
        cost_synergy_fraction=Decimal("0.03"),
        new_debt_rate=Decimal("0.07"),
        funding=Funding(Decimal("0.3"), Decimal("0.5"), Decimal("0.2")),
        ppe_share=Decimal("0.15"),
        intangibles_share=Decimal("0.25"),
    )
    return {
        "rnd_change": rnd_change(
            baseline,
            RndTerms(
                timing=Timing(2, ramp_quarters=2),
                fraction_of_budget=Decimal("0.25"),
                adoption_delay_quarters=8,
            ),
        ),
        "workforce_restructure": workforce_restructure(
            baseline,
            WorkforceTerms(
                timing=Timing(2, lag_quarters=1, ramp_quarters=2),
                headcount_change=Decimal("-0.10"),
                payroll_to_revenue=Decimal("0.30"),
                one_off_cost_months=Decimal(6),
                savings_realization=Decimal("0.8"),
                productivity_loss=Decimal("0.05"),
            ),
        ),
        "acquisition": acquisition(baseline, deal),
        "acquisition_failed": acquisition(baseline, replace(deal, completed=False)),
        "divestiture": divestiture(
            baseline,
            DivestitureTerms(
                timing=Timing(2, lag_quarters=2, ramp_quarters=2),
                revenue_fraction=Decimal("0.15"),
                unit_ebitda_margin=Decimal("0.10"),
                proceeds=Decimal(900),
                separation_cost_fraction=Decimal("0.02"),
                stranded_cost_fraction=Decimal("0.4"),
                tax_rate_on_gain=Decimal("0.25"),
                debt_paydown=Decimal("0.5"),
                cash_retained=Decimal("0.5"),
                shareholder_distribution=Decimal(0),
            ),
        ),
        "capex_expansion": capex_expansion(
            baseline,
            CapexTerms(
                timing=Timing(2, lag_quarters=4, ramp_quarters=4),
                investment=Decimal(800),
                capacity_increase=Decimal("0.3"),
                useful_life_years=15,
                utilization=Decimal("0.75"),
                new_debt_rate=Decimal("0.07"),
                funding=Funding(Decimal("0.5"), Decimal("0.5"), Decimal(0)),
            ),
        ),
        "debt_refinance": debt_refinance(
            baseline,
            RefinanceTerms(
                timing=Timing(2),
                amount=Decimal(500),
                new_rate=Decimal("0.04"),
                new_maturity_years=7,
                fee_fraction=Decimal("0.01"),
            ),
        ),
    }


def illustrative_capital() -> CapitalCost:
    return CapitalCost(
        risk_free=Decimal("0.04"),
        equity_risk_premium=Decimal("0.05"),
        beta=Decimal("1.1"),
        pre_tax_cost_of_debt=Decimal("0.06"),
        tax_rate=Decimal("0.25"),
        debt_weight=Decimal("0.25"),
    )
