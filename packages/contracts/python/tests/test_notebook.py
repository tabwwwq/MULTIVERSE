"""Saved scenarios, revisions, report snapshots and the notebook file (Stage 07)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts import NotebookExport

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "notebook" / "valid-export.json"
VALID: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _mutated(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(json.dumps(VALID))
    change(payload)
    return payload


def _scenario(payload: dict[str, Any]) -> dict[str, Any]:
    scenario: dict[str, Any] = payload["scenarios"][0]
    return scenario


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report: dict[str, Any] = payload["reports"][0]
    return report


def test_the_shared_export_is_valid_and_round_trips() -> None:
    parsed = NotebookExport.model_validate_json(json.dumps(VALID))

    again = NotebookExport.model_validate_json(parsed.model_dump_json())

    assert again == parsed
    assert parsed.scenarios[0].revisions[1].parent_revision == 1


BROKEN: dict[str, Callable[[dict[str, Any]], None]] = {
    "revision numbers with a gap": lambda p: _scenario(p)["revisions"][1].update(revision=3),
    "parent after the child": lambda p: _scenario(p)["revisions"][1].update(parent_revision=2),
    "first revision with a parent": lambda p: _scenario(p)["revisions"][0].update(
        parent_revision=1, revision=1
    ),
    "result ID without a run": lambda p: _scenario(p)["revisions"][0].update(
        result_id="2d7c9e41-5b3a-4f6e-8c1d-9a0b7e6f5c34"
    ),
    "run result without an ID": lambda p: _scenario(p)["revisions"][0].update(
        result_status="completed"
    ),
    "tag with capitals": lambda p: _scenario(p).update(tags=["R&D"]),
    "duplicate tags": lambda p: _scenario(p).update(tags=["rnd", "rnd"]),
    "name with surrounding spaces": lambda p: _scenario(p).update(name=" Northwind "),
    "revisions for two companies": lambda p: _scenario(p)["revisions"][1]["draft"].update(
        company_id="a7c2e9d4-1f3b-4c8a-b5e6-0d9f2a7c3e18"
    ),
    "report content changed after export": lambda p: _report(p).update(content="edited"),
    "report from a revision not marked exported": lambda p: _scenario(p)["revisions"][0].update(
        exported=False
    ),
    "report for a missing revision": lambda p: _report(p)["source"].update(revision=9),
    "manifest of another revision": lambda p: _report(p)["manifest"].update(revision=2),
    "demo report without _DEMO": lambda p: _report(p).update(file_name="northwind.md"),
    "file from a newer version": lambda p: p.update(schema_version=2),
    "duplicate scenario IDs": lambda p: p["scenarios"].append(p["scenarios"][0]),
    "unknown field such as a token": lambda p: p.update(api_token="secret"),
    "broken decision inside a revision": lambda p: _scenario(p)["revisions"][0]["draft"][
        "decision"
    ]["financing"].update(debt="0.3"),
}


@pytest.mark.parametrize("change", BROKEN.values(), ids=BROKEN.keys())
def test_broken_notebook_files_are_rejected(change: Callable[[dict[str, Any]], None]) -> None:
    with pytest.raises(ValidationError):
        NotebookExport.model_validate_json(json.dumps(_mutated(change)))
