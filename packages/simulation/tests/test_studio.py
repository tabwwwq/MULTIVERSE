"""The studio: values add up, stress cases reconcile, and the report says what it is."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from multiverse_simulation.example import default_decision, illustrative_case
from multiverse_simulation.run import simulate
from multiverse_simulation.studio import (
    _stress_paths,
    build_studio,
    central_baseline,
    shifted,
)
from multiverse_simulation.summary import build_report
from pydantic import ValidationError

from multiverse_contracts.decisions import DECISION_MODELS, DecisionModel
from multiverse_contracts.simulation import (
    SimulationCase,
    SimulationReport,
    SimulationSettings,
)
from multiverse_contracts.valuation import (
    QualityCheck,
    StudioInputs,
    StudioScenario,
    ValuationReport,
)
from multiverse_finance.engine import project
from multiverse_finance.exact import FinanceError

ROOT = Path(__file__).parents[3]
CASE = illustrative_case(horizon=12, history_quarters=40)
STAMP = datetime(2026, 11, 6, tzinfo=UTC)


def decision(**changes: object) -> DecisionModel:
    payload = default_decision("acquisition") | changes
    return DECISION_MODELS["acquisition"].model_validate_json(  # type: ignore[return-value]
        json.dumps(payload)
    )


DECISION = decision(financing={"cash": "0.2", "debt": "0.8", "equity": "0"})


def inputs(**changes: object) -> StudioInputs:
    values: dict[str, object] = {
        "exit_multiple": "11",
        "other_senior_claims": "50000000",
        "wacc_steps": ("-0.01", "0", "0.01"),
        "growth_steps": ("-0.01", "0", "0.01"),
        "margin_points": "0.02",
        "growth_points": "0.02",
        "capex_points": "0.01",
        "scenarios": (
            StudioScenario(
                scenario="bear", label="Bear", weight="0.25", growth_shift=-0.02, margin_shift=-0.02
            ),
            StudioScenario(
                scenario="base", label="Base", weight="0.5", growth_shift=0.0, margin_shift=0.0
            ),
            StudioScenario(
                scenario="bull", label="Bull", weight="0.25", growth_shift=0.02, margin_shift=0.02
            ),
        ),
        "scenario_paths": 100,
        "seed": 3,
        "maturity_wall_quarter": 6,
    } | changes
    return StudioInputs(**values)  # type: ignore[arg-type]


def simulation() -> SimulationReport:
    settings = SimulationSettings(paths=100, seed=3)
    frame, _ = simulate(CASE, DECISION, settings)
    return build_report(
        CASE, DECISION, settings, frame, code_version="test", created_at=STAMP, seconds=1.0
    )


SIMULATION = simulation()
REPORT = build_studio(CASE, DECISION, inputs(), SIMULATION, code_version="test", created_at=STAMP)
VIEW = REPORT.views[1]


def close(left: str | Decimal, right: str | Decimal, tolerance: str = "0.05") -> bool:
    return abs(Decimal(left) - Decimal(right)) <= Decimal(tolerance)


def test_a_report_says_what_its_numbers_are_not() -> None:
    assert REPORT.value_label == "Model value, not a verified market value"
    assert REPORT.sensitivity_label == "Predictive sensitivity, not causal"


def test_the_contract_refuses_another_label() -> None:
    payload = json.loads(REPORT.model_dump_json())
    payload["value_label"] = "Fair market value"
    with pytest.raises(ValidationError):
        ValuationReport.model_validate_json(json.dumps(payload))


def test_the_contract_refuses_a_report_with_a_failed_required_check() -> None:
    failed = QualityCheck(key="must_currency", label="x", passed=False, detail="x")
    broken = REPORT.model_copy(update={"checks": (failed,)})
    with pytest.raises(ValidationError, match="required check"):
        ValuationReport.model_validate_json(broken.model_dump_json())


def test_each_row_can_be_redone_from_its_own_columns() -> None:
    for row in VIEW.rows:
        fcff = (
            Decimal(row.ebit)
            - Decimal(row.tax_on_ebit)
            + Decimal(row.d_and_a)
            - Decimal(row.capex)
            - Decimal(row.delta_nwc)
            + Decimal(row.transactions)
        )
        assert close(fcff, row.fcff)
        assert close(Decimal(row.fcff) * Decimal(str(row.discount_factor)), row.present_value, "50")


def test_the_quarters_add_up_to_the_present_value_of_the_forecast() -> None:
    total = sum(Decimal(row.present_value) for row in VIEW.rows)
    assert close(total, VIEW.present_explicit, "1")


def test_ev_is_the_forecast_plus_the_terminal_value_by_each_method() -> None:
    for row in VIEW.terminals:
        assert row.present_terminal is not None
        assert row.enterprise_value is not None
        assert close(
            Decimal(VIEW.present_explicit) + Decimal(row.present_terminal), row.enterprise_value
        )


def test_each_terminal_method_is_checked_against_the_other() -> None:
    gordon, leaving = VIEW.terminals
    assert gordon.implied_multiple is not None
    assert leaving.implied_growth is not None
    assert gordon.terminal_share is not None


def test_ev_and_equity_value_are_different_outputs_joined_by_the_bridge() -> None:
    bridge = VIEW.bridge
    assert bridge.enterprise_value is not None
    assert bridge.equity_value is not None
    expected = (
        Decimal(bridge.enterprise_value)
        - Decimal(bridge.debt)
        + Decimal(bridge.cash)
        - Decimal(bridge.other_senior_claims)
        + Decimal(bridge.non_operating_assets)
    )
    assert close(expected, bridge.equity_value)
    assert bridge.equity_value != bridge.enterprise_value
    assert Decimal(bridge.other_senior_claims) == 50_000_000


def test_the_matrix_centre_is_the_value_of_the_report() -> None:
    centre = next(
        cell
        for cell in VIEW.sensitivity
        if cell.wacc == pytest.approx(REPORT.wacc, abs=1e-4) and cell.growth == 0.025
    )
    assert centre.enterprise_value is not None
    assert close(centre.enterprise_value, VIEW.bridge.enterprise_value or "0", "1")


def test_the_equity_of_a_cell_goes_through_the_same_bridge() -> None:
    centre = next(
        cell
        for cell in VIEW.sensitivity
        if cell.wacc == pytest.approx(REPORT.wacc, abs=1e-4) and cell.growth == 0.025
    )
    assert centre.equity_value is not None
    assert close(centre.equity_value, VIEW.bridge.equity_value or "0", "1")


def test_the_exit_multiple_applies_to_ebitda_before_one_offs_of_the_last_year() -> None:
    year = sum(Decimal(row.adjusted_ebitda) for row in VIEW.rows[-4:])
    leaving = VIEW.terminals[1]
    assert leaving.terminal_value is not None
    assert close(leaving.terminal_value, year * Decimal("11"), "1")


def test_a_cell_at_or_above_wacc_has_no_value() -> None:
    wide = inputs(growth_steps=("-0.01", "0", "0.1"))
    built = build_studio(CASE, DECISION, wide, SIMULATION, code_version="test")
    empty = [cell for cell in built.views[1].sensitivity if cell.enterprise_value is None]
    assert empty
    assert all(cell.wacc <= cell.growth for cell in empty)
    assert all(cell.equity_value is None for cell in empty)


def test_tornado_is_widest_first_and_each_driver_moves_value_the_right_way() -> None:
    base = Decimal(REPORT.base_value)
    spreads = [Decimal(row.high_value) - Decimal(row.low_value) for row in REPORT.tornado]
    assert spreads == sorted(spreads, reverse=True)
    assert {row.driver for row in REPORT.tornado} == {"margin", "growth", "capex", "synergies"}
    for row in REPORT.tornado:
        assert Decimal(row.low_value) < base < Decimal(row.high_value)


def test_scenarios_are_ordered_and_their_weights_make_a_whole() -> None:
    bear, middle, bull = REPORT.scenarios
    assert Decimal(bear.ev_p50) < Decimal(middle.ev_p50) < Decimal(bull.ev_p50)
    assert sum(Decimal(row.weight) for row in REPORT.scenarios) == 1
    assert bear.covenant_probability >= bull.covenant_probability


def test_the_weighted_value_lies_between_the_scenarios() -> None:
    means = [Decimal(row.ev_mean) for row in REPORT.scenarios]
    assert min(means) < Decimal(REPORT.weighted_enterprise_value) < max(means)


def test_weights_that_are_not_a_whole_are_refused() -> None:
    scenarios = inputs().scenarios
    skewed = (
        scenarios[0].model_copy(update={"weight": "0.5"}),
        scenarios[1],
        scenarios[2],
    )
    with pytest.raises(FinanceError, match="shares_sum"):
        build_studio(CASE, DECISION, inputs(scenarios=skewed), SIMULATION, code_version="test")


def test_every_stress_case_of_the_protocol_is_there() -> None:
    assert {row.key for row in REPORT.stress} == {
        "revenue_fall",
        "margin_compression",
        "rates_up",
        "working_capital",
        "refinancing_closed",
        "synergies_late",
        "deal_fails",
        "recession",
    }


def test_each_stress_hurts_where_it_should() -> None:
    rows = {row.key: row for row in REPORT.stress}
    base = Decimal(REPORT.base_value)
    assert Decimal(rows["revenue_fall"].enterprise_value or "0") < base
    assert Decimal(rows["recession"].enterprise_value or "0") < Decimal(
        rows["revenue_fall"].enterprise_value or "0"
    )
    assert rows["rates_up"].ev_change == "0.00"
    assert (rows["rates_up"].lowest_interest_cover or 0) < (
        rows["deal_fails"].lowest_interest_cover or 0
    )
    assert Decimal(rows["refinancing_closed"].lowest_cash) < Decimal(rows["rates_up"].lowest_cash)


def test_each_stress_row_says_what_its_own_path_did() -> None:
    paths = _stress_paths(central_baseline(CASE), DECISION, inputs())
    for row in REPORT.stress:
        path = paths[row.key][1]
        leverage = [
            period.credit.leverage.value
            for period in path.periods
            if period.credit.leverage.value is not None
        ]
        assert row.peak_leverage == pytest.approx(float(max(leverage)), abs=1e-3)
        lowest = min(period.balance.cash for period in path.periods)
        assert close(row.lowest_cash, lowest)


def test_a_margin_stress_takes_margin_away() -> None:
    paths = _stress_paths(central_baseline(CASE), DECISION, inputs())
    stressed = paths["margin_compression"][1].periods[-1].income
    calm = paths["rates_up"][1].periods[-1].income
    own = dict(stressed.segments)["total"]
    assert float(calm.ebitda - stressed.ebitda) == pytest.approx(float(own) * 0.03)


def test_the_maturity_wall_falls_due_in_its_quarter_with_lenders_shut() -> None:
    paths = _stress_paths(central_baseline(CASE), DECISION, inputs())
    quarter = paths["refinancing_closed"][1].periods[5]
    assert quarter.cash_flow.debt_repaid >= 500_000_000
    assert quarter.cash_flow.debt_drawn == 0


def test_the_adverse_story_is_told_from_the_numbers_of_the_path() -> None:
    recession = next(row for row in REPORT.stress if row.key == "recession")
    story = " ".join(REPORT.adverse_story)
    assert recession.peak_leverage is not None
    assert f"{recession.peak_leverage:.1f}x" in story
    assert "conditional on the assumed model" in story


def test_required_checks_pass_and_are_all_there() -> None:
    keys = {check.key for check in REPORT.checks}
    assert keys >= {
        "must_reconciliation",
        "must_currency",
        "must_discount_factors",
        "must_wacc_above_growth",
        "must_value_adds_up",
        "must_scenario_weights",
        "must_matrix_direction",
        "terminal_growth_bound",
        "terminal_share",
        "terminal_methods",
    }
    assert all(check.passed for check in REPORT.checks if check.key.startswith("must_"))


def test_a_warning_can_fail_and_the_report_still_stands() -> None:
    wild = shifted(CASE).model_copy(
        update={"capital": CASE.capital.model_copy(update={"terminal_growth": "0.055"})}
    )
    built = build_studio(wild, DECISION, inputs(), SIMULATION, code_version="test")
    bound = next(check for check in built.checks if check.key == "terminal_growth_bound")
    assert bound.passed is False


def test_the_same_inputs_give_the_same_report_whatever_the_clock() -> None:
    again = build_studio(
        CASE,
        DECISION,
        inputs(),
        SIMULATION,
        code_version="test",
        created_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert again.manifest.valuation_id == REPORT.manifest.valuation_id
    assert again.views == REPORT.views
    assert again.scenarios == REPORT.scenarios
    assert again.stress == REPORT.stress


def test_other_inputs_are_another_report() -> None:
    other = build_studio(CASE, DECISION, inputs(exit_multiple="9"), SIMULATION, code_version="test")
    assert other.manifest.valuation_id != REPORT.manifest.valuation_id


def test_a_shifted_case_moves_only_what_it_says() -> None:
    moved = shifted(CASE, margin=0.01)
    assert moved.central.margin[0] == pytest.approx(CASE.central.margin[0] + 0.01)
    assert moved.central.growth == CASE.central.growth
    assert moved.drivers.capex_ratio == CASE.drivers.capex_ratio


def test_the_central_path_has_no_shock() -> None:
    baseline = central_baseline(CASE)
    assert all(quarter.rate_shift == 0 for quarter in baseline.quarters)
    assert project(baseline).periods


@pytest.mark.parametrize(
    "path", sorted((ROOT / "data" / "valuation").glob("report-*.json")), ids=lambda p: p.name
)
def test_the_committed_report_matches_its_case_and_run(path: Path) -> None:
    built = ValuationReport.model_validate_json(path.read_bytes())
    manifest = built.manifest
    data = ROOT / "data" / "simulation"
    case = SimulationCase.model_validate_json((data / f"{manifest.case_id}.json").read_bytes())
    run = next(
        report
        for report in (
            SimulationReport.model_validate_json(item.read_bytes())
            for item in data.glob("report-*.json")
        )
        if report.manifest.report_id == manifest.simulation_report_id
    )
    assert run.manifest.case_sha256 == manifest.case_sha256
    assert case.company_name == built.company_name
    assert all(check.passed for check in built.checks if check.key.startswith("must_"))
    assert built.inputs.diluted_shares is not None
