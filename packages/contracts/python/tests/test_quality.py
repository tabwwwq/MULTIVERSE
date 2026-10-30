"""Gate B contracts: a check and a manifest that would overstate the data are refused (Stage 14)."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.quality import CompanyDecision, GateCheck, GateManifest


def check(status: str = "pass", **extra: Any) -> dict[str, Any]:
    return {
        "check_id": "leakage",
        "title": "Leakage proof",
        "status": status,
        "summary": "identical",
        **extra,
    }


def manifest(**change: Any) -> dict[str, Any]:
    sha = "cd" * 32
    data = {
        "dataset_id": f"gate-b-20261028-{sha[:12]}",
        "sha256": sha,
        "data_cutoff": "2026-10-29T03:59:59.999999Z",
        "view": "vintage",
        "target_metric": "revenue",
        "first_origin": "2010-03-31",
        "last_origin": "2026-09-30",
        "companies": [{"cik": "0000000001", "name": "Synthetic", "include": True, "reasons": []}],
        "example_counts": [
            {
                "history_quarters": 12,
                "horizon_quarters": 4,
                "examples": 40,
                "companies": 1,
                "origins": 40,
            }
        ],
        "pit_snapshot_id": f"pit-20261028-{'ab' * 6}",
        "synthetic_macro": True,
        "checks": [check()],
        "verdict": "passed",
        "verdict_reasons": [],
        "contracts_version": "0.12.0",
        "created_at": "2026-10-30T12:00:00Z",
    }
    data.update(change)
    return data


def validates(model: type[Any], data: dict[str, Any]) -> Any:
    return model.model_validate_json(json.dumps(data))


def test_the_examples_are_valid() -> None:
    validates(GateManifest, manifest())
    validates(GateCheck, check("blocked", findings=["10 companies"]))


def test_a_check_that_does_not_pass_shows_what_it_found() -> None:
    with pytest.raises(ValidationError, match="shows what it found"):
        validates(GateCheck, check("warning"))
    with pytest.raises(ValidationError, match="at most 40"):
        validates(GateCheck, check("warning", findings=[f"case {i}" for i in range(41)]))


def test_an_excluded_company_says_why() -> None:
    with pytest.raises(ValidationError, match="states why"):
        validates(CompanyDecision, {"cik": "0000000001", "name": "X", "include": False})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"dataset_id": "gate-b-20261028-000000000000"}, "named by its hash"),
        ({"first_origin": "2027-01-01"}, "origins run forward"),
        ({"checks": [check("blocked", findings=["x"])]}, "blocked exactly when"),
        ({"verdict": "blocked", "verdict_reasons": ["x"]}, "blocked exactly when"),
        ({"checks": [check("warning", findings=["x"])]}, "passed_with_warnings"),
        ({"verdict": "passed_with_warnings"}, "says why"),
        ({"view": "latest"}, "never latest"),
    ],
)
def test_the_verdict_follows_the_checks(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validates(GateManifest, manifest(**change))
