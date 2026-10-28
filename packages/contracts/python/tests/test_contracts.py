"""Contract rules checked against shared fixtures in packages/contracts/fixtures/."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from multiverse_contracts import MetricValue, ReproducibilityManifest, ScenarioDraft

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
MODELS: dict[str, type[BaseModel]] = {
    "MetricValue": MetricValue,
    "ReproducibilityManifest": ReproducibilityManifest,
    "ScenarioDraft": ScenarioDraft,
}


def _cases(file_name: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads((FIXTURES / file_name).read_text(encoding="utf-8"))
    return cases


@pytest.mark.parametrize("case", _cases("valid.json"), ids=lambda case: case["name"])
def test_valid_payload_roundtrips(case: dict[str, Any]) -> None:
    model = MODELS[case["model"]]
    parsed = model.model_validate_json(json.dumps(case["payload"]))

    again = model.model_validate_json(parsed.model_dump_json())

    assert again == parsed


@pytest.mark.parametrize("case", _cases("invalid.json"), ids=lambda case: case["name"])
def test_invalid_payload_is_rejected(case: dict[str, Any]) -> None:
    model = MODELS[case["model"]]

    with pytest.raises(ValidationError) as caught:
        model.model_validate_json(json.dumps(case["payload"]))

    # Decision cases name the rule they break; the web validator reports the same code.
    if "code" in case:
        codes = {error["type"] for error in caught.value.errors()}
        assert f"[{case['code']}]" in str(caught.value) or case["code"] in codes


def test_contracts_are_immutable() -> None:
    case = _cases("valid.json")[0]
    value = MetricValue.model_validate_json(json.dumps(case["payload"]))

    with pytest.raises(ValidationError):
        value.metric = "ebitda"  # type: ignore[misc]


def test_money_is_serialized_as_a_decimal_string() -> None:
    case = _cases("valid.json")[0]
    value = MetricValue.model_validate_json(json.dumps(case["payload"]))

    dumped = json.loads(value.model_dump_json())

    assert dumped["quantity"]["value"] == "4213587912"
