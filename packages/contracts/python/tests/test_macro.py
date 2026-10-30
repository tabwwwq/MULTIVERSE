"""Macro contracts: an observation and a join cell that would mislead are refused (Stage 13)."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.macro import MacroCell, MacroObservation


def observation() -> dict[str, Any]:
    return {
        "series_id": "fred:CPIAUCSL",
        "period_start": "2021-12-01",
        "period_end": "2021-12-31",
        "value": "278.802",
        "available_from": "2022-01-13T04:59:59.999999Z",
        "available_to": "2023-02-15T04:59:59.999999Z",
        "basis": "vintage",
        "source_vintage": "2022-01-12",
    }


def cell() -> dict[str, Any]:
    return {
        "cik": "0000000001",
        "calendar_quarter": "2021Q4",
        "lag": 0,
        "window_start": "2021-10-01",
        "window_end": "2021-12-31",
        "feature": "us_10y_yield",
        "series_id": "fred:DGS10",
        "transform": "end_of_period",
        "state": "observed",
        "mask": True,
        "value": "1.52",
        "inputs": [
            {
                "period_start": "2021-12-30",
                "period_end": "2021-12-30",
                "value": "1.52",
                "available_from": "2022-01-01T04:59:59.999999Z",
                "basis": "vintage",
            }
        ],
    }


def validates(model: type[Any], data: dict[str, Any]) -> Any:
    return model.model_validate_json(json.dumps(data))


def test_the_examples_are_valid() -> None:
    validates(MacroObservation, observation())
    validates(MacroCell, cell())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("period_end", "2021-11-30", "starts before it ends"),
        ("available_to", "2022-01-13T04:59:59.999999Z", "ends after it starts"),
    ],
)
def test_an_observation_keeps_its_periods_in_order(field: str, value: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validates(MacroObservation, {**observation(), field: value})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"mask": False}, "mask is true exactly"),
        ({"value": None}, "has a value exactly when"),
        ({"inputs": []}, "names the observations"),
        ({"window_end": "2021-09-30"}, "starts before it ends"),
    ],
)
def test_a_cell_keeps_mask_value_and_inputs_consistent(
    change: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        validates(MacroCell, {**cell(), **change})


def test_a_value_is_never_made_of_an_estimated_release() -> None:
    data = cell()
    data["inputs"][0]["basis"] = "estimated"
    with pytest.raises(ValidationError, match="evidenced"):
        validates(MacroCell, data)


def test_an_empty_cell_says_why_and_is_never_zero() -> None:
    empty = {**cell(), "state": "not_yet_released", "mask": False, "value": None, "inputs": []}
    with pytest.raises(ValidationError, match="states why"):
        validates(MacroCell, empty)
    validates(MacroCell, {**empty, "reason": "2021-12-30 was not published by the cutoff"})
    with pytest.raises(ValidationError, match="has a value exactly when"):
        validates(MacroCell, {**empty, "value": "0", "reason": "x"})
