"""Point-in-time contracts: rules a value, a panel cell and a snapshot must pass (Stage 12)."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.pit import (
    EntityAttribute,
    PanelCell,
    PitSnapshotManifest,
    PitValue,
)

Mutation = Callable[[dict[str, Any]], None]

SOURCE = {
    "concept": "us-gaap:Revenues",
    "unit": "USD",
    "period_start": "2024-10-01",
    "period_end": "2024-12-31",
    "value": "130",
    "accession": "0000000001-25-000001",
    "form": "10-K",
    "filed": "2025-02-14",
}


def pit_value() -> dict[str, Any]:
    return {
        "value": {
            "cik": "0000000001",
            "metric": "revenue",
            "fiscal_year": 2024,
            "fiscal_period": "Q4",
            "period_kind": "duration",
            "period_start": "2024-10-01",
            "period_end": "2024-12-31",
            "revision": "latest",
            "value": "130",
            "unit": "USD",
            "currency": "USD",
            "concept": "us-gaap:Revenues",
            "method": "reported",
            "accession": "0000000001-25-000001",
            "filed": "2025-02-14",
            "sources": [SOURCE],
            "quality": "info",
        },
        "known_from": "2025-02-14T21:30:00Z",
        "known_to": None,
        "change": "first_known",
        "timings": [
            {
                "accession": "0000000001-25-000001",
                "known_at": "2025-02-14T21:30:00Z",
                "precision": "accepted",
            }
        ],
    }


def cell() -> dict[str, Any]:
    return {
        "cik": "0000000001",
        "calendar_quarter": "2024Q4",
        "quarter_end": "2024-12-31",
        "lag": 0,
        "metric": "revenue",
        "state": "observed",
        "mask": True,
        "value": "130",
        "unit": "USD",
        "currency": "USD",
        "fiscal_year": 2024,
        "fiscal_period": "Q4",
        "period_start": "2024-10-01",
        "period_end": "2024-12-31",
        "method": "reported",
        "concept": "us-gaap:Revenues",
        "accession": "0000000001-25-000001",
        "known_from": "2025-02-14T21:30:00Z",
    }


def manifest() -> dict[str, Any]:
    sha = "ab" * 32
    return {
        "snapshot_id": f"pit-20250331-{sha[:12]}",
        "sha256": sha,
        "cutoff": "2025-04-01T03:59:59.999999Z",
        "cutoff_label": "2025-03-31",
        "view": "vintage",
        "quarters": 2,
        "ciks": ["0000000001"],
        "metrics": ["revenue", "cfo"],
        "cells": 4,
        "state_counts": [{"state": "observed", "cells": 3}, {"state": "not_yet_filed", "cells": 1}],
        "contracts_version": "0.9.0",
        "inputs": [],
        "alerts": 0,
        "created_at": "2026-10-30T12:00:00Z",
    }


def validates(model: type[Any], data: dict[str, Any]) -> Any:
    return model.model_validate_json(json.dumps(data))


def test_the_examples_are_valid() -> None:
    validates(PitValue, pit_value())
    validates(PanelCell, cell())
    validates(PitSnapshotManifest, manifest())


def _set(path: str, value: Any) -> Mutation:
    def apply(data: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        target: Any = data
        for name in parents:
            target = target[int(name)] if isinstance(target, list) else target[name]
        target[last] = value

    return apply


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_set("known_to", "2025-02-14T21:30:00Z"), "ends after it starts"),
        (_set("timings", []), "every source filing"),
        (_set("timings.0.known_at", "2025-02-15T00:00:00Z"), "never known before"),
    ],
)
def test_a_pit_value_is_never_known_before_its_sources(mutation: Mutation, message: str) -> None:
    data = pit_value()
    mutation(data)
    with pytest.raises(ValidationError, match=message):
        validates(PitValue, data)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_set("mask", False), "mask is true exactly"),
        (_set("value", None), "has a value exactly when"),
        (_set("known_from", None), "when it became known"),
        (_set("period_end", "2025-03-31"), "near its calendar quarter end"),
    ],
)
def test_a_cell_keeps_mask_state_and_value_consistent(mutation: Mutation, message: str) -> None:
    data = cell()
    mutation(data)
    with pytest.raises(ValidationError, match=message):
        validates(PanelCell, data)


def test_an_empty_cell_states_why_and_is_never_zero() -> None:
    empty = {
        **cell(),
        "state": "not_yet_filed",
        "mask": False,
        "value": None,
        "reason": "the quarter's 10-Q or 10-K was not public at the cutoff",
    }
    validates(PanelCell, empty)
    with pytest.raises(ValidationError, match="states why"):
        validates(PanelCell, {**empty, "reason": None})
    with pytest.raises(ValidationError, match="has a value exactly when"):
        validates(PanelCell, {**empty, "value": "0"})


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_set("view", "latest"), "never latest"),
        (_set("snapshot_id", "pit-20250331-000000000000"), "named by its hash"),
        (_set("cells", 5), "add up"),
        (_set("metrics", ["revenue"]), "complete"),
        (_set("created_at", "2025-03-01T00:00:00Z"), "after its cutoff"),
    ],
)
def test_a_snapshot_is_point_in_time_complete_and_named_by_its_hash(
    mutation: Mutation, message: str
) -> None:
    data = manifest()
    mutation(data)
    with pytest.raises(ValidationError, match=message):
        validates(PitSnapshotManifest, data)


def test_an_attribute_stops_after_it_starts() -> None:
    data = {
        "cik": "0000000001",
        "attribute": "ticker",
        "value": "ABC",
        "effective_from": "2020-06-01",
        "effective_to": "2020-06-01",
        "observed_at": "2026-10-29T19:00:00Z",
        "source": "synthetic",
    }
    with pytest.raises(ValidationError, match="stops applying"):
        validates(EntityAttribute, data)
    validates(EntityAttribute, {**data, "effective_to": None})
