"""What a report says, and what it refuses to say."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
from multiverse_simulation.example import default_decision, illustrative_case
from multiverse_simulation.run import ALTERNATE, BASELINE, METRICS, RISKS, Frame, simulate
from multiverse_simulation.summary import (
    _wilson_upper,
    build_report,
    drawn_correlation,
    ev_change,
    quarter_ends,
    report_identity,
)
from pydantic import ValidationError

from multiverse_contracts.decisions import DECISION_MODELS, DecisionModel
from multiverse_contracts.primitives import ResultMode
from multiverse_contracts.simulation import (
    CONDITIONAL_LABEL,
    SimulationCase,
    SimulationReport,
    SimulationSettings,
)

DATA = Path(__file__).parents[3] / "data" / "simulation"
CASE = illustrative_case(horizon=8, history_quarters=40)
SETTINGS = SimulationSettings(paths=600, seed=3, batch_paths=200)
STAMP = datetime(2026, 11, 6, tzinfo=UTC)


def decision(**changes: object) -> DecisionModel:
    payload = default_decision("acquisition") | changes
    return DECISION_MODELS["acquisition"].model_validate_json(  # type: ignore[return-value]
        json.dumps(payload)
    )


DECISION = decision(financing={"cash": "0.1", "debt": "0.9", "equity": "0"})
FRAME, _ = simulate(CASE, DECISION, SETTINGS)


def report(
    frame: Frame = FRAME, settings: SimulationSettings = SETTINGS, stamp: datetime = STAMP
) -> SimulationReport:
    return build_report(
        CASE, DECISION, settings, frame, code_version="test", created_at=stamp, seconds=1.0
    )


REPORT = report()


def test_a_report_is_labelled_conditional_and_not_validated() -> None:
    assert REPORT.validation == "conditional_non_validated"
    assert REPORT.probability_label == CONDITIONAL_LABEL
    assert REPORT.result.calibrated is False
    assert REPORT.result.uncertainty_type == "conditional_model_quantiles"


def test_the_contract_refuses_a_calibrated_claim() -> None:
    claimed = REPORT.result.model_copy(
        update={"calibrated": True, "mode": ResultMode.EMPIRICAL_FORECAST}
    )
    payload = REPORT.model_copy(update={"result": claimed}).model_dump_json()
    with pytest.raises(ValidationError, match="conditional"):
        SimulationReport.model_validate_json(payload)


def test_the_contract_refuses_another_label() -> None:
    payload = REPORT.model_dump()
    payload["validation"] = "validated"
    with pytest.raises(ValidationError):
        SimulationReport.model_validate(payload)


def test_a_synthetic_case_gives_a_demo_result() -> None:
    assert REPORT.result.mode == "demo"
    assert REPORT.result.mock is False
    assert REPORT.result.data_origin == "synthetic"


def test_quantiles_are_ordered_in_every_quarter_of_every_scenario() -> None:
    for metric in REPORT.result.metrics:
        for series in (*metric.forecasts, *metric.changes):
            for point in series.points:
                assert Decimal(point.p10) <= Decimal(point.p50) <= Decimal(point.p90)
            assert len(series.points) == CASE.horizon


def test_a_paired_change_is_computed_path_by_path() -> None:
    index = METRICS.index("revenue")
    change = FRAME.metrics[ALTERNATE, :, -1, index] - FRAME.metrics[BASELINE, :, -1, index]
    metric = next(m for m in REPORT.result.metrics if m.metric == "revenue")
    point = metric.changes[0].points[-1]
    assert float(point.p50) == pytest.approx(float(np.quantile(change, 0.5)), abs=0.01)


def test_the_quantile_of_a_difference_is_not_the_difference_of_quantiles() -> None:
    index = METRICS.index("ebitda")
    base = FRAME.metrics[BASELINE, :, -1, index]
    alternate = FRAME.metrics[ALTERNATE, :, -1, index]
    difference = float(np.quantile(alternate - base, 0.9))
    subtraction = float(np.quantile(alternate, 0.9) - np.quantile(base, 0.9))
    assert difference != pytest.approx(subtraction, rel=1e-3)


def test_risks_cover_both_scenarios_with_their_monte_carlo_error() -> None:
    assert len(REPORT.risks) == 2 * len(RISKS)
    for row in REPORT.risks:
        index = RISKS.index(row.risk)
        scenario = BASELINE if row.scenario == "baseline" else ALTERNATE
        expected = float(FRAME.risks[scenario, :, index].mean())
        assert row.probability == pytest.approx(expected, abs=1e-5)
        spread = (expected * (1 - expected) / SETTINGS.paths) ** 0.5
        assert row.standard_error == pytest.approx(spread, abs=1e-5)
        assert row.upper_95 >= row.probability


def test_the_monte_carlo_error_of_a_risk_is_binomial() -> None:
    risks = FRAME.risks.copy()
    risks[:] = False
    risks[ALTERNATE, :150, 0] = True
    frame = Frame(
        FRAME.metrics,
        FRAME.enterprise,
        FRAME.equity,
        risks,
        FRAME.tail,
        FRAME.redraws,
        FRAME.clipped,
        FRAME.done,
    )
    row = next(r for r in report(frame).risks if r.scenario == "alt_a" and r.risk == RISKS[0])
    assert row.probability == 0.25
    assert row.standard_error == pytest.approx((0.25 * 0.75 / 600) ** 0.5, abs=1e-5)


def test_a_change_of_value_is_the_alternate_minus_the_baseline() -> None:
    expected = FRAME.enterprise[ALTERNATE, 3] - FRAME.enterprise[BASELINE, 3]
    assert ev_change(FRAME)[3] == expected


def test_no_event_on_n_paths_still_leaves_room_for_a_small_probability() -> None:
    assert _wilson_upper(0.0, 1000) == pytest.approx(0.00383, abs=1e-4)
    assert _wilson_upper(0.0, 10_000) < _wilson_upper(0.0, 1000)


def test_values_are_ordered_and_a_change_is_paired() -> None:
    for row in REPORT.values:
        assert row.p1 is not None
        assert row.p99 is not None
        points = [Decimal(row.p1), Decimal(row.p10), Decimal(row.p50), Decimal(row.p90)]
        assert [*points, Decimal(row.p99)] == sorted([*points, Decimal(row.p99)])
    change = next(row for row in REPORT.values if row.metric == "ev_change")
    assert change.mean is not None
    assert float(change.mean) == pytest.approx(float(np.nanmean(ev_change(FRAME))), abs=0.01)


def test_undefined_value_is_counted_and_left_out() -> None:
    holes = Frame(
        FRAME.metrics,
        FRAME.enterprise.copy(),
        FRAME.equity.copy(),
        FRAME.risks,
        FRAME.tail,
        FRAME.redraws,
        FRAME.clipped,
        FRAME.done,
    )
    holes.enterprise[:, :60] = np.nan
    row = next(r for r in report(holes).values if r.metric == "enterprise_value")
    assert row.undefined_share == pytest.approx(0.1)


def test_convergence_lists_each_size_up_to_the_run_with_its_error() -> None:
    sizes = {row.paths for row in REPORT.convergence}
    assert sizes == {500, 600}
    final = [row for row in REPORT.convergence if row.paths == 600]
    assert all(row.gap_to_final == 0 for row in final)
    assert all(row.standard_error >= 0 for row in REPORT.convergence)


def test_tails_are_the_worst_paths_in_order_with_their_drivers() -> None:
    changes = [float(row.ev_change) for row in REPORT.tails]
    assert changes == sorted(changes)
    assert changes[0] == pytest.approx(float(np.nanmin(ev_change(FRAME))), abs=0.01)
    assert {driver.name for driver in REPORT.tails[0].drivers} >= {"growth_shock", "deal_closed"}


def test_the_change_distribution_holds_every_path_and_says_under_what() -> None:
    for distribution in REPORT.result.distributions:
        assert sum(item.count for item in distribution.bins) == SETTINGS.paths
        assert 0 <= float(distribution.probability_above_zero) <= 1


def test_a_small_run_is_flagged() -> None:
    assert any("tail probabilities" in flag for flag in REPORT.diagnostics.flags)


def test_a_setting_outside_the_planning_range_is_named() -> None:
    wild = decision(deal_cost_fraction="0.1")
    frame, _ = simulate(CASE, wild, SimulationSettings(paths=30, seed=3))
    built = build_report(
        CASE,
        wild,
        SimulationSettings(paths=30, seed=3),
        frame,
        code_version="test",
        created_at=STAMP,
        seconds=1.0,
    )
    assert any("Out of distribution" in flag for flag in built.diagnostics.flags)


def test_correlation_of_the_draw_is_measured_against_the_history() -> None:
    historical, simulated = drawn_correlation(CASE, SETTINGS)
    assert simulated == pytest.approx(historical, abs=0.05)
    assert REPORT.diagnostics.historical_correlation == pytest.approx(historical, abs=1e-3)


def test_finance_identities_were_checked_on_every_statement_path() -> None:
    assert REPORT.diagnostics.path_identities_checked == 2 * SETTINGS.paths


def test_the_manifest_names_everything_needed_to_replay() -> None:
    manifest = REPORT.manifest
    assert manifest.settings == SETTINGS
    assert manifest.case_id == CASE.case_id
    assert manifest.finance_version
    assert manifest.simulation_version
    assert "block bootstrap" in manifest.shock_model
    assert REPORT.result.manifest.seed == SETTINGS.seed
    assert REPORT.result.manifest.causal_status == "assumption_based"


def test_equal_inputs_give_an_equal_report_whatever_the_clock_says() -> None:
    later = report(stamp=datetime(2027, 1, 1, tzinfo=UTC))
    assert later.manifest.report_id == REPORT.manifest.report_id
    assert later.risks == REPORT.risks
    assert later.result.metrics == REPORT.result.metrics


def test_another_seed_is_another_report() -> None:
    other = SETTINGS.model_copy(update={"seed": 4})
    assert report_identity(CASE, DECISION, other)[0] != REPORT.manifest.report_id


def test_quarter_ends_are_month_ends_after_the_balance_date() -> None:
    from datetime import date

    ends = quarter_ends(date(2026, 6, 30), 3)
    assert ends == (date(2026, 9, 30), date(2026, 12, 31), date(2027, 3, 31))


@pytest.mark.parametrize("path", sorted(DATA.glob("case-*.json")), ids=lambda p: p.name)
def test_the_committed_cases_are_valid_and_say_how_each_input_is_known(path: Path) -> None:
    case = SimulationCase.model_validate_json(path.read_bytes())
    assert case.inputs
    assert {item.origin for item in case.inputs} >= {"observed", "assumed"}
    assert case.history
    assert all(point.filed_at <= case.as_of for point in case.history)
    assert all(row.quarter_end <= case.as_of for row in case.shocks.rows)


@pytest.mark.parametrize("path", sorted(DATA.glob("report-*.json")), ids=lambda p: p.name)
def test_the_committed_reports_match_their_case(path: Path) -> None:
    built = SimulationReport.model_validate_json(path.read_bytes())
    case = SimulationCase.model_validate_json(
        (DATA / f"{built.manifest.case_id}.json").read_bytes()
    )
    settings = built.manifest.settings
    decision_model = built.result.scenarios[1].decision
    assert report_identity(case, decision_model, settings)[1] == built.manifest.case_sha256
    assert built.validation == "conditional_non_validated"
    assert built.result.mode == "empirical_forecast"
    assert built.diagnostics.paths == settings.paths
