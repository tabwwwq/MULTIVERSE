"""An invented case for tests and the demo. SYNTHETIC: no number here is observed."""

from datetime import date, timedelta

import numpy as np

from multiverse_contracts.interventions import CATALOG
from multiverse_contracts.primitives import DataOrigin
from multiverse_contracts.simulation import (
    CapitalInputs,
    CaseDrivers,
    CaseInput,
    CaseOpening,
    CasePolicy,
    CaseTranche,
    CentralPath,
    ShockHistory,
    ShockRow,
    SimulationCase,
)
from multiverse_contracts.version import CONTRACTS_VERSION

VARIABLES = (
    "rate_change",
    "gdp_change",
    "sector_growth",
    "firm_growth",
    "sector_margin",
    "firm_margin",
)
LOADINGS = np.array(
    [
        [0.0030, 0.0, 0.0, 0.0],
        [0.0040, 0.0060, 0.0, 0.0],
        [0.0040, 0.0180, 0.0140, 0.0],
        [0.0, 0.0, 0.0, 0.0300],
        [0.0005, 0.0040, 0.0050, 0.0],
        [0.0, 0.0, 0.0, 0.0080],
    ]
)
"""Four invented factors: rates, activity, sector and firm. Sector columns load on activity."""


def _history(quarters: int, seed: int) -> ShockHistory:
    rng = np.random.default_rng(seed)
    factors = np.zeros((quarters, 4))
    state = np.zeros(4)
    for quarter in range(quarters):
        state = 0.5 * state + rng.standard_t(6, size=4)
        factors[quarter] = state
    table = factors @ LOADINGS.T
    start = date(2011, 3, 31)
    rows = tuple(
        ShockRow(
            quarter_end=start + timedelta(days=91 * quarter),
            values=tuple(round(float(value), 6) for value in table[quarter]),
        )
        for quarter in range(quarters)
    )
    return ShockHistory(
        variables=VARIABLES,
        rows=rows,
        persistence_growth=0.7,
        persistence_margin=0.8,
        mean_block_quarters=4.0,
        base_short_rate=0.04,
        peers=40,
        method="Invented: an AR(1) of four factors with Student-t noise.",
    )


def illustrative_case(
    horizon: int = 12, history_quarters: int = 60, seed: int = 7
) -> SimulationCase:
    """A company close to the example of the finance engine, in dollars as the contract is."""
    million = 1_000_000
    return SimulationCase(
        contracts_version=CONTRACTS_VERSION,
        case_id="case-synthetic-northwind",
        company_id="5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13",
        company_name="Northwind Precision (synthetic)",
        as_of=date(2026, 6, 30),
        balance_date=date(2026, 6, 30),
        currency="USD",
        data_origin=DataOrigin.SYNTHETIC,
        opening=CaseOpening(
            cash=str(500 * million),
            trade_nwc=str(400 * million),
            ppe=str(2000 * million),
            intangibles=str(300 * million),
            goodwill=str(700 * million),
            non_operating_assets=str(100 * million),
            tranches=(
                CaseTranche(
                    name="senior_notes",
                    principal=str(1000 * million),
                    annual_rate="0.05",
                    maturity_quarter=8,
                ),
                CaseTranche(
                    name="term_loan",
                    principal=str(500 * million),
                    annual_rate="0.06",
                    floating=True,
                ),
            ),
            trailing_ebitda=(str(190 * million), str(195 * million), str(200 * million)),
            trailing_interest=(str(20 * million), str(20 * million), str(20 * million)),
        ),
        policy=CasePolicy(
            tax_rate="0.25",
            depreciation_rate="0.10",
            amortization_rate="0.20",
            cash_yield="0.02",
            minimum_cash=str(100 * million),
            revolver_limit=str(300 * million),
            revolver_rate="0.07",
            marginal_debt_rate="0.065",
            dividend_payout="0.30",
            max_leverage="3.5",
            min_interest_cover="3",
        ),
        drivers=CaseDrivers(
            last_year_revenue=tuple(str(value * million) for value in (940, 960, 980, 1000)),
            rd_ratio=0.08,
            cogs_share=0.76,
            capex_ratio=0.05,
            nwc_ratio=0.10,
        ),
        central=CentralPath(
            growth=(0.06,) * horizon,
            margin=(0.20,) * horizon,
            growth_source="Invented.",
            margin_source="Invented.",
        ),
        shocks=_history(history_quarters, seed),
        capital=CapitalInputs(
            risk_free="0.04",
            equity_risk_premium="0.05",
            beta="1.1",
            pre_tax_cost_of_debt="0.06",
            tax_rate="0.25",
            debt_weight="0.25",
            terminal_growth="0.025",
        ),
        inputs=(CaseInput(name="everything", origin="assumed", note="An invented company."),),
    )


def default_decision(kind: str) -> dict[str, object]:
    """The catalog defaults of one decision type, as JSON."""
    spec = CATALOG.spec(kind)
    unit = spec.magnitude.default_unit or spec.magnitude.units[0].unit
    unit_spec = next(u for u in spec.magnitude.units if u.unit == unit)
    decision: dict[str, object] = {
        "type": spec.type.value,
        "magnitude": {"value": unit_spec.default_value, "unit": unit.value},
        "timing": {
            "announcement_date": "2026-07-01",
            "effective_date": "2026-10-01",
            "lag_quarters": int(str(spec.lag_quarters.default)),
            "ramp_quarters": int(str(spec.ramp_quarters.default)),
        },
    }
    for parameter in spec.parameters:
        default = parameter.default
        if isinstance(default, str):
            decision[parameter.key] = int(default) if parameter.integer else default
        else:
            decision[parameter.key] = default.model_dump()
    if spec.share_group is not None:
        group = spec.share_group
        decision[group.key] = {
            member.key: share for member, share in zip(group.members, group.defaults, strict=True)
        }
    return decision
