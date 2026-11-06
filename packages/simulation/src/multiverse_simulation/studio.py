"""The valuation and risk studio: one report from the statements of Stage 21 and paths of Stage 22.

Views, tornado and stress cases run on the central path, with no shock and the deal closed: they
explain the mechanics. Scenarios and risks come from paths. Every number comes from reconciled
statements, and the report repeats what it checked.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import pairwise

import numpy as np

from multiverse_contracts.decisions import DecisionModel
from multiverse_contracts.distributions import FixedValue, TriangularRange, UniformRange
from multiverse_contracts.simulation import SimulationCase, SimulationReport, SimulationSettings
from multiverse_contracts.valuation import (
    SENSITIVITY_LABEL,
    VALUE_LABEL,
    BridgeView,
    DcfRow,
    DebtRow,
    QualityCheck,
    ScenarioRow,
    SensitivityCell,
    StressRow,
    StudioInputs,
    StudioScenario,
    TerminalRow,
    TornadoRow,
    ValuationManifest,
    ValuationReport,
    ValuationView,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_finance import __version__ as finance_version
from multiverse_finance.checks import residuals
from multiverse_finance.decisions import Accounting, Pick, central, plan_for
from multiverse_finance.engine import project
from multiverse_finance.exact import ZERO, exact
from multiverse_finance.ledger import Plan
from multiverse_finance.model import Baseline
from multiverse_finance.statements import Period, StatementPath
from multiverse_finance.stress import (
    margin_compression,
    maturity_wall,
    rate_shock,
    refinancing_closed,
    revenue_shock,
    working_capital_absorption,
)
from multiverse_finance.valuation import (
    Dcf,
    discount_factor,
    discounted,
    enterprise_value,
    equity_bridge,
    implied_growth,
    with_exit_multiple,
)
from multiverse_finance.valuation import weighted_value as weighted
from multiverse_simulation import __version__ as simulation_version
from multiverse_simulation.paths import Prepared, path_baseline
from multiverse_simulation.run import ALTERNATE, RISKS, simulate
from multiverse_simulation.shocks import PathShocks
from multiverse_simulation.summary import quarter_ends

YEAR = 4
SYNERGY_DELAY = 8
REVENUE_FALL = Decimal("0.2")
MARGIN_POINTS = Decimal("0.03")
RATE_POINTS = Decimal("0.02")
NWC_POINTS = Decimal("0.05")
TERMINAL_SHARE_WARNING = Decimal("0.75")
METHOD_GAP_WARNING = Decimal("0.15")
TIGHT = Decimal("1e-20")
ACCOUNTING = Accounting(target_follows_baseline=True)


def money(value: Decimal) -> str:
    return f"{value:.2f}"


def _label(day: date) -> str:
    return f"{day.year} Q{(day.month - 1) // 3 + 1}"


def shifted(
    case: SimulationCase, growth: float = 0.0, margin: float = 0.0, capex: float = 0.0
) -> SimulationCase:
    """The same case with its central path moved: an assumption, labelled as one."""
    central_path = case.central.model_copy(
        update={
            "growth": tuple(value + growth for value in case.central.growth),
            "margin": tuple(value + margin for value in case.central.margin),
        }
    )
    drivers = case.drivers.model_copy(update={"capex_ratio": case.drivers.capex_ratio + capex})
    return case.model_copy(update={"central": central_path, "drivers": drivers})


def central_baseline(case: SimulationCase) -> Baseline:
    """The path with no shock at all."""
    zeros = np.zeros(case.horizon)
    quiet = PathShocks(zeros, zeros, zeros, np.zeros((case.horizon, 1)))
    return path_baseline(Prepared.of(case), quiet)[0]


def _plans(
    baseline: Baseline,
    decision: DecisionModel,
    closed: bool = True,
    pick: Pick = central,
    accounting: Accounting = ACCOUNTING,
) -> list[Plan]:
    return [plan_for(decision, baseline, accounting, closed, pick)]


@dataclass(frozen=True)
class Valued:
    """A path and what it is worth by each terminal method."""

    path: StatementPath
    gordon: Dcf
    exit: Dcf
    recurring: tuple[Decimal, ...]
    ebitda: tuple[Decimal, ...]


def _value(path: StatementPath, prepared: Prepared, multiple: Decimal) -> Valued:
    wacc = prepared.capital.wacc
    last = path.periods[-YEAR:]
    recurring = tuple(period.free_cash.fcff_recurring for period in last)
    ebitda = tuple(period.income.adjusted_ebitda for period in last)
    flows = [period.free_cash.fcff for period in path.periods]
    return Valued(
        path,
        enterprise_value(path, prepared.capital, prepared.growth),
        with_exit_multiple(flows, ebitda, wacc, multiple),
        recurring,
        ebitda,
    )


def _row(period: Period, day: date, wacc: Decimal) -> DcfRow:
    income, cash, free = period.income, period.cash_flow, period.free_cash
    factor = discount_factor(period.quarter, wacc)
    return DcfRow(
        quarter=period.quarter,
        period_end=day,
        label=_label(day),
        revenue=money(income.revenue),
        ebitda=money(income.ebitda),
        adjusted_ebitda=money(income.adjusted_ebitda),
        ebit=money(income.ebit),
        tax_on_ebit=money(free.tax_on_ebit),
        d_and_a=money(income.d_and_a),
        capex=money(cash.capex),
        delta_nwc=money(cash.delta_nwc),
        transactions=money(free.transactions),
        fcff=money(free.fcff),
        fcff_recurring=money(free.fcff_recurring),
        discount_factor=round(float(factor), 8),
        present_value=money(free.fcff * factor),
    )


def _debt(period: Period, day: date) -> DebtRow:
    balance, credit = period.balance, period.credit
    leverage, cover = credit.leverage.value, credit.interest_cover.value
    return DebtRow(
        period_end=day,
        label=_label(day),
        cash=money(balance.cash),
        term_debt=money(balance.term_debt),
        revolver=money(balance.revolver),
        shortfall=money(balance.shortfall),
        net_debt=money(balance.net_debt),
        interest_expense=money(period.income.interest_expense),
        leverage=round(float(leverage), 3) if leverage is not None else None,
        interest_cover=round(float(cover), 3) if cover is not None else None,
    )


def _optional(value: Decimal | None) -> str | None:
    return money(value) if value is not None else None


def _terminals(valued: Valued, wacc: Decimal) -> tuple[TerminalRow, TerminalRow]:
    gordon, leaving = valued.gordon, valued.exit
    year = sum(valued.ebitda, ZERO)
    multiple = None
    if gordon.terminal_value is not None and year > 0:
        multiple = round(float(gordon.terminal_value / year), 3)
    growth = None
    if leaving.terminal_value is not None:
        found = implied_growth(leaving.terminal_value, valued.recurring, wacc)
        growth = round(float(found), 5) if found is not None else None

    def share(dcf: Dcf) -> float | None:
        value = dcf.terminal_share.value
        return round(float(value), 5) if value is not None else None

    return (
        TerminalRow(
            method="gordon",
            label="Perpetual growth",
            terminal_value=_optional(gordon.terminal_value),
            present_terminal=_optional(gordon.present_terminal),
            enterprise_value=_optional(gordon.enterprise_value),
            terminal_share=share(gordon),
            implied_multiple=multiple,
            reason=gordon.reason,
        ),
        TerminalRow(
            method="exit_multiple",
            label="Exit multiple",
            terminal_value=_optional(leaving.terminal_value),
            present_terminal=_optional(leaving.present_terminal),
            enterprise_value=_optional(leaving.enterprise_value),
            terminal_share=share(leaving),
            implied_growth=growth,
            reason=leaving.reason,
        ),
    )


def _sensitivity(
    valued: Valued, prepared: Prepared, inputs: StudioInputs, other: Decimal
) -> tuple[SensitivityCell, ...]:
    flows = [period.free_cash.fcff for period in valued.path.periods]
    opening = prepared.opening
    net_claims = opening.term_debt + opening.revolver - opening.cash + other
    net_claims -= opening.non_operating_assets
    cells = []
    for wacc_step in inputs.wacc_steps:
        for growth_step in inputs.growth_steps:
            wacc = prepared.capital.wacc + Decimal(wacc_step)
            growth = prepared.growth + Decimal(growth_step)
            value = None
            if wacc > growth:
                value = discounted(flows, valued.recurring, wacc, growth).enterprise_value
            cells.append(
                SensitivityCell(
                    wacc=round(float(wacc), 5),
                    growth=round(float(growth), 5),
                    enterprise_value=_optional(value),
                    equity_value=_optional(value - net_claims) if value is not None else None,
                )
            )
    return tuple(cells)


def _view(
    scenario: str,
    label: str,
    valued: Valued,
    case: SimulationCase,
    prepared: Prepared,
    inputs: StudioInputs,
) -> ValuationView:
    wacc = prepared.capital.wacc
    ends = quarter_ends(case.balance_date, case.horizon)
    periods = valued.path.periods
    other = Decimal(inputs.other_senior_claims)
    bridge = equity_bridge(valued.gordon, prepared.opening, other)
    return ValuationView(
        scenario=scenario,  # type: ignore[arg-type]
        label=label,
        rows=tuple(_row(period, day, wacc) for period, day in zip(periods, ends, strict=True)),
        debt=tuple(_debt(period, day) for period, day in zip(periods, ends, strict=True)),
        present_explicit=money(valued.gordon.present_value),
        terminals=_terminals(valued, wacc),
        bridge=BridgeView(
            enterprise_value=_optional(bridge.enterprise_value),
            debt=money(bridge.debt),
            cash=money(bridge.cash),
            other_senior_claims=money(bridge.other_senior_claims),
            non_operating_assets=money(bridge.non_operating_assets),
            equity_value=_optional(bridge.equity_value),
        ),
        sensitivity=_sensitivity(valued, prepared, inputs, other),
    )


def _ev(path: StatementPath, prepared: Prepared) -> Decimal:
    value = enterprise_value(path, prepared.capital, prepared.growth).enterprise_value
    if value is None:
        raise ValueError("the central path has no value: the studio needs one to move from")
    return value


def _points(sign: str, share: float) -> str:
    amount = share * 100
    return f"{sign}{amount:g} point{'' if amount == 1 else 's'}"


def _tornado(
    case: SimulationCase, decision: DecisionModel, inputs: StudioInputs, prepared: Prepared
) -> tuple[TornadoRow, ...]:
    margin, growth = float(inputs.margin_points), float(inputs.growth_points)
    capex = float(inputs.capex_points)

    def value(variant: SimulationCase, pick: Pick = central) -> Decimal:
        baseline = central_baseline(variant)
        return _ev(project(baseline, _plans(baseline, decision, pick=pick)), prepared)

    rows = [
        TornadoRow(
            driver="margin",
            label="EBITDA margin",
            low_label=_points("−", margin),
            high_label=_points("+", margin),
            low_value=money(value(shifted(case, margin=-margin))),
            high_value=money(value(shifted(case, margin=margin))),
        ),
        TornadoRow(
            driver="growth",
            label="Revenue growth",
            low_label=_points("−", growth),
            high_label=_points("+", growth),
            low_value=money(value(shifted(case, growth=-growth))),
            high_value=money(value(shifted(case, growth=growth))),
        ),
        TornadoRow(
            driver="capex",
            label="CAPEX of revenue",
            low_label=_points("+", capex),
            high_label=_points("−", capex),
            low_value=money(value(shifted(case, capex=capex))),
            high_value=money(value(shifted(case, capex=-capex))),
        ),
    ]
    synergy = getattr(decision, "cost_synergy_fraction", None)
    if isinstance(synergy, TriangularRange | UniformRange):

        def at(point: str) -> Pick:
            def pick(name: str, shape: FixedValue | UniformRange | TriangularRange) -> Decimal:
                return Decimal(point) if name == "cost_synergy_fraction" else central(name, shape)

            return pick

        rows.append(
            TornadoRow(
                driver="synergies",
                label="Cost synergies",
                low_label=f"{float(synergy.low) * 100:g}% of target revenue",
                high_label=f"{float(synergy.high) * 100:g}% of target revenue",
                low_value=money(value(case, at(synergy.low))),
                high_value=money(value(case, at(synergy.high))),
            )
        )
    return tuple(sorted(rows, key=lambda row: Decimal(row.low_value) - Decimal(row.high_value)))


def _scenario(
    case: SimulationCase, decision: DecisionModel, scenario: StudioScenario, inputs: StudioInputs
) -> ScenarioRow:
    variant = shifted(case, growth=scenario.growth_shift, margin=scenario.margin_shift)
    settings = SimulationSettings(paths=inputs.scenario_paths, seed=inputs.seed)
    frame, _ = simulate(variant, decision, settings)
    value = frame.enterprise[ALTERNATE]
    value = value[np.isfinite(value)]
    equity = frame.equity[ALTERNATE]
    p10, p50, p90 = np.quantile(value, (0.1, 0.5, 0.9))
    risks = frame.risks[ALTERNATE]
    return ScenarioRow(
        scenario=scenario.scenario,
        label=scenario.label,
        weight=scenario.weight,
        paths=settings.paths,
        ev_p10=f"{p10:.2f}",
        ev_p50=f"{p50:.2f}",
        ev_p90=f"{p90:.2f}",
        ev_mean=f"{value.mean():.2f}",
        equity_p50=f"{np.nanquantile(equity, 0.5):.2f}",
        covenant_probability=round(float(risks[:, RISKS.index("covenant_breach")].mean()), 5),
        shortfall_probability=round(float(risks[:, RISKS.index("funding_shortfall")].mean()), 5),
    )


def _stress_row(
    key: str,
    label: str,
    path: StatementPath,
    prepared: Prepared,
    base: Decimal,
    ends: Sequence[date],
) -> StressRow:
    value = enterprise_value(path, prepared.capital, prepared.growth).enterprise_value
    leverage = [
        p.credit.leverage.value for p in path.periods if p.credit.leverage.value is not None
    ]
    cover = [
        p.credit.interest_cover.value
        for p in path.periods
        if p.credit.interest_cover.value is not None
    ]
    breach = next(
        (
            _label(ends[index])
            for index, period in enumerate(path.periods)
            if any("breach" in alert for alert in period.alerts)
        ),
        None,
    )
    return StressRow(
        key=key,
        label=label,
        enterprise_value=_optional(value),
        ev_change=_optional(value - base) if value is not None else None,
        lowest_cash=money(min(p.balance.cash for p in path.periods)),
        peak_leverage=round(float(max(leverage)), 3) if leverage else None,
        lowest_interest_cover=round(float(min(cover)), 3) if cover else None,
        first_breach=breach,
        peak_shortfall=money(max(p.balance.shortfall for p in path.periods)),
    )


def _stress_paths(
    baseline: Baseline, decision: DecisionModel, inputs: StudioInputs
) -> dict[str, tuple[str, StatementPath, Baseline]]:
    def through(variant: Baseline, closed: bool = True, books: Accounting = ACCOUNTING):  # type: ignore[no-untyped-def]
        return project(variant, _plans(variant, decision, closed, accounting=books)), variant

    recession = rate_shock(
        margin_compression(revenue_shock(baseline, REVENUE_FALL), MARGIN_POINTS), RATE_POINTS
    )
    wall = refinancing_closed(maturity_wall(baseline, inputs.maturity_wall_quarter))
    late = replace(ACCOUNTING, synergy_delay_quarters=SYNERGY_DELAY)
    found: dict[str, tuple[str, tuple[StatementPath, Baseline]]] = {
        "revenue_fall": ("Revenue −20%", through(revenue_shock(baseline, REVENUE_FALL))),
        "margin_compression": (
            "Gross margin −3 points",
            through(margin_compression(baseline, MARGIN_POINTS)),
        ),
        "rates_up": ("Rates +200 bps", through(rate_shock(baseline, RATE_POINTS))),
        "working_capital": (
            "Working capital takes 5 more points of revenue",
            through(working_capital_absorption(baseline, NWC_POINTS)),
        ),
        "refinancing_closed": (
            f"Lenders shut, debt due in quarter {inputs.maturity_wall_quarter}",
            through(wall),
        ),
        "synergies_late": ("Synergies two years late", through(baseline, books=late)),
        "deal_fails": ("The deal fails", through(baseline, closed=False)),
        "recession": ("Recession: all of revenue, margin and rates", through(recession)),
    }
    return {key: (label, *pair) for key, (label, pair) in found.items()}


def _usd(value: Decimal) -> str:
    return f"USD {value / 1_000_000:,.0f} million"


def _adverse(
    path: StatementPath,
    row: StressRow,
    base: Decimal,
    ends: Sequence[date],
    limit: Decimal,
    floor: Decimal,
    covenant: float,
) -> tuple[str, ...]:
    """Told only from the statements of the path: each sentence is a number that can be checked."""
    story = [
        "Revenue falls 20% and the gross margin loses 3 points from the first quarter, and "
        "rates rise 200 basis points, on top of the deal."
    ]
    if row.peak_leverage is not None:
        peak = max(
            (p for p in path.periods if p.credit.leverage.value is not None),
            key=lambda p: p.credit.leverage.value or ZERO,
        )
        where = _label(ends[peak.quarter - 1])
        side = "above" if row.peak_leverage > float(limit) else "within"
        story.append(
            f"Net debt / EBITDA peaks at {row.peak_leverage:.1f}x in {where}, {side} the "
            f"limit of {limit:.1f}x."
        )
    if row.lowest_interest_cover is not None:
        side = "below" if row.lowest_interest_cover < float(floor) else "above"
        story.append(
            f"Interest cover falls to {row.lowest_interest_cover:.1f}x, {side} the floor of "
            f"{floor:.1f}x."
        )
    if row.first_breach is not None:
        story.append(f"The first covenant breach comes in {row.first_breach}.")
    shortfall = Decimal(row.peak_shortfall)
    if shortfall > 0:
        story.append(f"Lenders leave a funding shortfall of up to {_usd(shortfall)}.")
    else:
        story.append(
            f"Cash stays at {_usd(Decimal(row.lowest_cash))} or above, with no funding shortfall."
        )
    if row.enterprise_value is not None:
        value = Decimal(row.enterprise_value)
        story.append(f"Enterprise value falls by {_usd(base - value)}, to {_usd(value)}.")
    story.append(
        f"For scale: on {covenant:.1%} of the simulated paths a covenant breaks, conditional on "
        "the assumed model, without this stress being imposed."
    )
    return tuple(story)


def _check(key: str, label: str, passed: bool, detail: str) -> QualityCheck:
    return QualityCheck(key=key, label=label, passed=passed, detail=detail)


def _checks(
    case: SimulationCase,
    prepared: Prepared,
    valued: Valued,
    baselines: Sequence[tuple[StatementPath, Baseline]],
    weighted_value: Decimal,
    scenario_means: Sequence[Decimal],
    weights: Sequence[Decimal],
    view: ValuationView,
) -> tuple[QualityCheck, ...]:
    wacc, growth = prepared.capital.wacc, prepared.growth
    worst = max(
        abs(item.value) for path, baseline in baselines for item in residuals(path, baseline)
    )
    gordon = valued.gordon
    assert gordon.enterprise_value is not None
    assert gordon.present_terminal is not None
    four = discount_factor(YEAR, wacc)
    adds = abs(gordon.present_value + gordon.present_terminal - gordon.enterprise_value)
    bridge = view.bridge
    equity = (
        Decimal(bridge.enterprise_value or "0")
        - Decimal(bridge.debt)
        + Decimal(bridge.cash)
        - Decimal(bridge.other_senior_claims)
        + Decimal(bridge.non_operating_assets)
        - Decimal(bridge.equity_value or "0")
    )
    cells = {(cell.wacc, cell.growth): cell for cell in view.sensitivity}
    rates = sorted({cell.wacc for cell in view.sensitivity})
    growths = sorted({cell.growth for cell in view.sensitivity})
    falling = all(
        Decimal(cells[(low, g)].enterprise_value or "0")
        > Decimal(cells[(high, g)].enterprise_value or "0")
        for g in growths
        for low, high in pairwise(rates)
        if cells[(high, g)].enterprise_value is not None
    )
    share = gordon.terminal_share.value
    exit_value = valued.exit.enterprise_value
    gap = (
        abs(gordon.enterprise_value / exit_value - 1)
        if exit_value is not None and exit_value > 0
        else None
    )
    return (
        _check(
            "must_reconciliation",
            "Statements reconcile",
            worst < Decimal("0.01"),
            f"{len(baselines)} central and stress paths, largest residual {worst:.2e} USD.",
        ),
        _check(
            "must_currency",
            "One currency",
            case.currency == "USD",
            f"Every amount is in {case.currency}; nothing is converted (D-04).",
        ),
        _check(
            "must_discount_factors",
            "Quarterly factors match the annual rate",
            abs(four - 1 / (1 + wacc)) < TIGHT
            and discount_factor(1, wacc) != 1 / (1 + wacc / YEAR),
            f"Four quarters at {wacc:.4%} compound to exactly one year; a quarter is not rate / 4.",
        ),
        _check(
            "must_wacc_above_growth",
            "WACC above terminal growth",
            wacc > growth,
            f"WACC {wacc:.2%}, terminal growth {growth:.2%}.",
        ),
        _check(
            "must_value_adds_up",
            "EV and the bridge add up",
            adds < TIGHT and abs(equity) < Decimal("0.02"),
            "Explicit years plus terminal value give EV; EV less claims gives equity value.",
        ),
        _check(
            "must_scenario_weights",
            "Scenario weights are a whole",
            sum(weights, ZERO) == 1
            and min(scenario_means) <= weighted_value <= max(scenario_means),
            "Weights add up to 100%, and the weighted value lies between the scenarios.",
        ),
        _check(
            "must_matrix_direction",
            "Value falls as WACC rises",
            falling,
            "In every column of the sensitivity matrix.",
        ),
        _check(
            "terminal_growth_bound",
            "Terminal growth at or below the risk-free rate",
            growth <= Decimal(case.capital.risk_free),
            f"Terminal growth {growth:.2%}, risk-free {Decimal(case.capital.risk_free):.2%}.",
        ),
        _check(
            "terminal_share",
            f"Terminal value below {TERMINAL_SHARE_WARNING:.0%} of EV",
            share is not None and share <= TERMINAL_SHARE_WARNING,
            f"It is {share:.1%} of EV: most of this value lies beyond the forecast."
            if share is not None
            else "Undefined.",
        ),
        _check(
            "terminal_methods",
            f"Terminal methods within {METHOD_GAP_WARNING:.0%} of each other",
            gap is not None and gap <= METHOD_GAP_WARNING,
            f"Perpetual growth and exit multiple differ by {gap:.1%}."
            if gap is not None
            else "No comparison is defined.",
        ),
    )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@exact
def build_studio(
    case: SimulationCase,
    decision: DecisionModel,
    inputs: StudioInputs,
    simulation: SimulationReport,
    *,
    code_version: str,
    created_at: datetime | None = None,
) -> ValuationReport:
    prepared = Prepared.of(case)
    multiple = Decimal(inputs.exit_multiple)
    baseline = central_baseline(case)
    ends = quarter_ends(case.balance_date, case.horizon)
    plain = _value(project(baseline), prepared, multiple)
    deal = _value(project(baseline, _plans(baseline, decision)), prepared, multiple)
    views = (
        _view("baseline", "Baseline", plain, case, prepared, inputs),
        _view("alt_a", "With the decision", deal, case, prepared, inputs),
    )
    base_value = _ev(deal.path, prepared)

    scenarios = tuple(_scenario(case, decision, item, inputs) for item in inputs.scenarios)
    means = [Decimal(row.ev_mean) for row in scenarios]
    weights = [Decimal(row.weight) for row in scenarios]
    weighted_ev = weighted(means, weights)

    paths = _stress_paths(baseline, decision, inputs)
    stress = tuple(
        _stress_row(key, label, path, prepared, base_value, ends)
        for key, (label, path, _) in paths.items()
    )
    recession = next(row for row in stress if row.key == "recession")
    covenant = next(
        row.probability
        for row in simulation.risks
        if row.risk == "covenant_breach" and row.scenario == "alt_a"
    )
    policy = prepared.policy
    limit = policy.max_leverage if policy.max_leverage is not None else ZERO
    floor = policy.min_interest_cover if policy.min_interest_cover is not None else ZERO
    story = _adverse(paths["recession"][1], recession, base_value, ends, limit, floor, covenant)

    checked = [(plain.path, baseline), (deal.path, baseline)]
    checked += [(path, variant) for _, path, variant in paths.values()]
    case_sha = _sha(case.model_dump_json())
    decision_sha = _sha(decision.model_dump_json())
    inputs_sha = _sha(inputs.model_dump_json())
    identity = "|".join(
        (
            case_sha,
            decision_sha,
            inputs_sha,
            simulation.manifest.report_id,
            finance_version,
            simulation_version,
            CONTRACTS_VERSION,
        )
    )
    return ValuationReport(
        contracts_version=CONTRACTS_VERSION,
        manifest=ValuationManifest(
            valuation_id=f"val-{case.as_of:%Y%m%d}-{_sha(identity)[:12]}",
            contracts_version=CONTRACTS_VERSION,
            finance_version=finance_version,
            simulation_version=simulation_version,
            code_version=code_version,
            case_id=case.case_id,
            case_sha256=case_sha,
            decision_sha256=decision_sha,
            inputs_sha256=inputs_sha,
            simulation_report_id=simulation.manifest.report_id,
            created_at=created_at or datetime.now(UTC),
        ),
        value_label=VALUE_LABEL,  # type: ignore[arg-type]
        sensitivity_label=SENSITIVITY_LABEL,  # type: ignore[arg-type]
        company_name=case.company_name,
        as_of=case.as_of,
        balance_date=case.balance_date,
        currency=case.currency,
        capital=case.capital,
        wacc=round(float(prepared.capital.wacc), 6),
        cost_of_equity=round(float(prepared.capital.cost_of_equity), 6),
        inputs=inputs,
        case_inputs=case.inputs,
        views=views,
        tornado=_tornado(case, decision, inputs, prepared),
        base_value=money(base_value),
        scenarios=scenarios,
        weighted_enterprise_value=money(weighted_ev),
        stress=stress,
        adverse_title="What the worst stress does, quarter by quarter",
        adverse_story=story,
        checks=_checks(
            case,
            prepared,
            deal,
            checked,
            weighted_ev,
            means,
            weights,
            views[1],
        ),
    )
