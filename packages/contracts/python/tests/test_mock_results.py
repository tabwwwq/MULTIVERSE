"""Scenario result contract and the Stage 06 mock results."""

import json
import random
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts import ScenarioResult
from multiverse_contracts.mock_results import (
    FIXTURE_PATH,
    HORIZON,
    SimPath,
    apply_effect,
    build_results,
    render,
)

RESULTS: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
COMPLETED = [result for result in RESULTS if result["status"] == "completed"]


def _metric(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(metric for metric in result["metrics"] if metric["metric"] == name)


def _mutated(change: Any) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(json.dumps(COMPLETED[0]))
    change(payload)
    return payload


def test_fixture_file_is_up_to_date() -> None:
    assert FIXTURE_PATH.read_text(encoding="utf-8") == render()


def test_the_same_seed_gives_identical_results() -> None:
    first = [result.model_dump_json() for result in build_results()]
    second = [result.model_dump_json() for result in build_results()]

    assert first == second


def test_every_result_is_a_labelled_demo_mock() -> None:
    for payload in RESULTS:
        result = ScenarioResult.model_validate_json(json.dumps(payload))
        assert result.mode == "demo"
        assert result.data_origin == "synthetic"
        assert result.mock is True
        assert result.calibrated is False


def test_a_zero_effect_leaves_every_path_equal_to_the_baseline() -> None:
    rng = random.Random(1)
    revenue = [rng.uniform(900, 1100) for _ in range(HORIZON)]
    ebitda = [value * 0.2 for value in revenue]
    fcf = [value * 0.7 for value in ebitda]
    debt, net_debt = 500.0, []
    for flow in fcf:
        debt -= flow
        net_debt.append(debt)
    base = SimPath(revenue, ebitda, fcf, net_debt)
    zero = {name: [0.0] * HORIZON for name in ("revenue", "ebitda", "fcf")}

    assert apply_effect(base, zero) == base


def test_alternates_share_the_baselines_shocks_across_results() -> None:
    # Same company, cutoff and seed: the baseline paths, and so their quantiles, coincide.
    rnd, capex = COMPLETED[0], COMPLETED[1]
    for name in ("revenue", "ebitda", "net_debt"):
        baseline = [
            next(s for s in _metric(result, name)["forecasts"] if s["scenario"] == "baseline")
            for result in (rnd, capex)
        ]
        assert baseline[0] == baseline[1]


def test_history_stops_at_what_was_public_on_the_cutoff() -> None:
    for result in COMPLETED:
        for metric in result["metrics"]:
            assert all(point["filed_at"] <= result["as_of"] for point in metric["observed"])


def test_the_quarter_ending_on_the_cutoff_is_forecast_when_filed_later() -> None:
    revenue = _metric(COMPLETED[0], "revenue")

    assert revenue["observed"][-1]["fiscal_label"] == "FY2022 Q3"
    assert revenue["forecasts"][0]["points"][0]["fiscal_label"] == "FY2022 Q4"


def test_percent_changes_are_omitted_where_the_baseline_can_cross_zero() -> None:
    units = {change["unit"] for change in _metric(COMPLETED[0], "net_debt")["changes"]}

    assert units == {"currency"}


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p["waterfalls"][0].update(end=str(int(p["waterfalls"][0]["end"]) + 1)),
        lambda p: p["metrics"][0]["forecasts"][0]["points"][0].update(p10="99999999999"),
        lambda p: p.update(calibrated=True),
        lambda p: p.update(mode="empirical_forecast"),
        lambda p: p.update(failure={"code": "x", "message": "x", "incident_id": "x"}),
        lambda p: p["metrics"][0]["observed"][-1].update(filed_at="2023-06-01"),
        lambda p: p["metrics"][0]["forecasts"][0]["points"].pop(),
        lambda p: p["scenarios"].pop(0),
        lambda p: p["distributions"][0]["bins"][1].update(low="1"),
    ],
    ids=[
        "waterfall does not add up",
        "p10 above p50",
        "demo claims calibration",
        "mock outside demo mode",
        "completed result with a failure",
        "history filed after the cutoff",
        "forecast shorter than the horizon",
        "no baseline first",
        "histogram bins with a gap",
    ],
)
def test_broken_results_are_rejected(change: Any) -> None:
    with pytest.raises(ValidationError):
        ScenarioResult.model_validate_json(json.dumps(_mutated(change)))


def test_a_failed_result_carries_an_incident_and_no_numbers() -> None:
    failed = next(result for result in RESULTS if result["status"] == "failed")

    assert failed["failure"]["incident_id"]
    assert failed["metrics"] == []
    payload = json.loads(json.dumps(failed))
    payload["metrics"] = COMPLETED[0]["metrics"]
    with pytest.raises(ValidationError):
        ScenarioResult.model_validate_json(json.dumps(payload))
