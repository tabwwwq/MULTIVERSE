"""Contracts of Stage 19: what makes an event an event."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.events import CorporateEvent, EventFunding, EventMagnitude, EventRegistry

SHA = "ab" * 32


def event(**changes: Any) -> dict[str, Any]:
    return {
        "event_id": "evt-0000000001-layoff-20240301",
        "cik": "0000000001",
        "company": "Company",
        "division": "D",
        "deregistered": False,
        "event_type": "layoff",
        "intention": "Cut 100 positions.",
        "magnitude": {"value": 100, "unit": "headcount", "measures": "Positions"},
        "completion": "announced",
        "stratum": "item_2_05",
        "evidence": [
            {
                "role": "announcement",
                "url": "https://www.sec.gov/Archives/edgar/data/1/x/doc.htm",
                "accession": "0000000001-24-000001",
                "form": "8-K",
                "filed_at": "2024-03-01T21:00:00Z",
                "locator": "Item 2.05",
                "summary": "A plan.",
                "document_sha256": SHA,
            }
        ],
        "reviews": [
            {
                "reviewer": "claude_ai",
                "kind": "ai",
                "decision": "confirmed",
                "confidence": "high",
                "reviewed_at": "2026-11-06T12:00:00Z",
            }
        ],
    } | changes


def parse(values: dict[str, Any]) -> CorporateEvent:
    return CorporateEvent.model_validate_json(json.dumps(values))


def test_a_valid_event_passes() -> None:
    assert parse(event()).event_type.value == "layoff"


def test_an_event_says_what_was_announced_or_done() -> None:
    with pytest.raises(ValidationError, match="intention, an execution"):
        parse(event(intention=None))


def test_completed_means_a_document_says_what_was_done() -> None:
    with pytest.raises(ValidationError, match="says what was executed"):
        parse(event(completion="completed"))
    assert parse(event(completion="completed", executed="Cut 100 positions.")).executed


def test_evidence_lives_on_the_sec_archive() -> None:
    values = event()
    values["evidence"][0]["url"] = "https://example.com/news"
    with pytest.raises(ValidationError):
        parse(values)


def test_an_event_needs_evidence_and_a_named_review() -> None:
    with pytest.raises(ValidationError):
        parse(event(evidence=[]))
    with pytest.raises(ValidationError):
        parse(event(reviews=[]))


def test_the_announcement_comes_from_a_document_of_the_event() -> None:
    assert parse(event(announced_at="2024-03-01T21:00:00Z")).announced_at is not None
    with pytest.raises(ValidationError, match="announcement moment"):
        parse(event(announced_at="2023-01-01T00:00:00Z"))


def test_a_magnitude_has_a_value_with_a_unit_or_neither() -> None:
    with pytest.raises(ValidationError, match="both a value and a unit"):
        EventMagnitude.model_validate_json('{"value": 40, "measures": "x"}')
    with pytest.raises(ValidationError, match="both a value and a unit"):
        EventMagnitude.model_validate_json('{"unit": "usd", "measures": "x"}')
    assert EventMagnitude.model_validate_json('{"measures": "x"}').value is None


def test_known_funding_shares_add_up_to_one() -> None:
    with pytest.raises(ValidationError, match="add up to one"):
        EventFunding.model_validate_json('{"cash": 0.4, "debt": 0.4}')
    assert EventFunding.model_validate_json('{"cash": 0.4, "debt": 0.6}').debt == 0.6


def test_event_ids_are_unique() -> None:
    values = {
        "registry_version": "0.1.0",
        "sample_id": "evs-20261106-abababababab",
        "guidelines": "guidelines.md",
        "events": [event(), event()],
    }
    with pytest.raises(ValidationError, match="unique"):
        EventRegistry.model_validate_json(json.dumps(values))
