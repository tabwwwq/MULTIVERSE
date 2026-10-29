"""NormalizedValue: the honesty rules every canonical number must pass (Stage 11)."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.normalized import NormalizedValue

Mutation = Callable[[dict[str, Any]], None]

SOURCE = {
    "concept": "us-gaap:Revenues",
    "unit": "USD",
    "period_start": "2024-01-01",
    "period_end": "2024-12-31",
    "value": "460",
    "accession": "0000000001-25-000001",
    "form": "10-K",
    "filed": "2025-02-14",
}


def derived() -> dict[str, Any]:
    """Q4 = FY - 9M of a synthetic company."""
    return {
        "cik": "0000000001",
        "metric": "revenue",
        "fiscal_year": 2024,
        "fiscal_period": "Q4",
        "period_kind": "duration",
        "period_start": "2024-10-01",
        "period_end": "2024-12-31",
        "revision": "original",
        "value": "130",
        "unit": "USD",
        "currency": "USD",
        "concept": "us-gaap:Revenues",
        "method": "fy_minus_nine_months",
        "accession": "0000000001-25-000001",
        "filed": "2025-02-14",
        "sources": [
            SOURCE,
            {
                **SOURCE,
                "period_end": "2024-09-30",
                "value": "330",
                "accession": "0000000001-24-000003",
                "form": "10-Q",
                "filed": "2024-10-25",
                "sign": -1,
            },
        ],
        "quality": "info",
    }


def missing() -> dict[str, Any]:
    data = derived()
    data.update(value=None, missing_reason="Q4 needs the fiscal year", method=None, sources=[])
    data.update(concept=None, accession=None, filed=None)
    return data


def validate(data: dict[str, Any]) -> NormalizedValue:
    return NormalizedValue.model_validate_json(json.dumps(data))


def test_a_derived_and_a_missing_value_are_accepted() -> None:
    assert validate(derived()).value == "130"
    assert validate(missing()).value is None


def _zero_for_missing(d: dict[str, Any]) -> None:
    d.update(missing(), value="0")


def _missing_without_reason(d: dict[str, Any]) -> None:
    d.update(missing(), missing_reason=None)


def _missing_with_sources(d: dict[str, Any]) -> None:
    d.update(missing(), sources=[SOURCE])


def _value_without_method(d: dict[str, Any]) -> None:
    d["method"] = None


def _reported_with_two_sources(d: dict[str, Any]) -> None:
    d["method"] = "reported"


def _derived_with_one_source(d: dict[str, Any]) -> None:
    d["sources"] = d["sources"][:1]
    d["value"] = "460"


def _sum_does_not_match(d: dict[str, Any]) -> None:
    d["value"] = "131"


def _knowledge_date_too_early(d: dict[str, Any]) -> None:
    d["filed"] = "2024-10-25"
    d["accession"] = "0000000001-24-000003"


def _foreign_accession(d: dict[str, Any]) -> None:
    d["accession"] = "0000000001-25-000009"


def _instant_with_start(d: dict[str, Any]) -> None:
    d["period_kind"] = "instant"


def _blocking_with_value(d: dict[str, Any]) -> None:
    d["quality"] = "blocking"


def _restated_without_original(d: dict[str, Any]) -> None:
    d.update(revision="latest", flags=["restated"])


def _original_value_on_original(d: dict[str, Any]) -> None:
    d.update(flags=["restated"], original_value="460")


def _calculated_without_formula(d: dict[str, Any]) -> None:
    d.update(method="calculated", concept=None)


def _no_concept(d: dict[str, Any]) -> None:
    d["concept"] = None


def _short_cik(d: dict[str, Any]) -> None:
    d["cik"] = "1"


@pytest.mark.parametrize(
    "mutate",
    [
        _zero_for_missing,
        _missing_without_reason,
        _missing_with_sources,
        _value_without_method,
        _reported_with_two_sources,
        _derived_with_one_source,
        _sum_does_not_match,
        _knowledge_date_too_early,
        _foreign_accession,
        _instant_with_start,
        _blocking_with_value,
        _restated_without_original,
        _original_value_on_original,
        _calculated_without_formula,
        _no_concept,
        _short_cik,
    ],
)
def test_a_dishonest_value_is_refused(mutate: Mutation) -> None:
    data = derived()
    mutate(data)
    with pytest.raises(ValidationError):
        validate(data)
