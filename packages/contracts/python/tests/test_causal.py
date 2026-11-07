"""Contracts of Stage 20: a graph that joins, and a study that cannot claim an effect."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.causal import CausalGraph, CausalStudy

SHA = "ab" * 32


def graph(**changes: Any) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "node_id": "action",
                "label": "Decision",
                "role": "action",
                "observed": True,
                "measured_by": "Registry",
            }
        ],
        "edges": [{"source": "action", "target": "action", "rationale": "x"}],
        "omitted": [],
    } | changes


def study(**changes: Any) -> dict[str, Any]:
    return {
        "study_id": f"cst-20261106-{SHA[:12]}",
        "sha256": SHA,
        "label": "feasibility_study_no_effect_estimated",
        "effects_estimated": 0,
        "outcomes_after_treatment_read": False,
        "data_cutoff": "2026-10-29T03:59:59Z",
        "dataset_id": "fds",
        "registry_version": "0.1.0",
        "sample_id": "evs",
        "audit_credible": False,
        "audit_blockers": ["x"],
        "graph": graph(),
        "rules": ["x"],
        "treatments": [
            {
                "treatment": "layoff",
                "estimand": "x",
                "assumptions": ["y"],
                "untested": ["z"],
                "events": 1,
                "usable": 0,
                "candidate_pool": 1,
                "controls": 1,
                "confounded_share": 0,
                "near_decision_share": 0,
                "divisions": {},
                "verdicts": [{"method": "matched_cohort", "feasible": False, "reasons": ["x"]}],
            }
        ],
        "findings": [],
        "seed": 1,
        "contracts_version": "0.22.0",
        "created_at": "2026-11-06T12:00:00Z",
    } | changes


def parse(values: dict[str, Any]) -> CausalStudy:
    return CausalStudy.model_validate_json(json.dumps(values))


def test_every_edge_joins_two_nodes() -> None:
    CausalGraph.model_validate_json(json.dumps(graph()))
    edges = [{"source": "action", "target": "nowhere", "rationale": "x"}]
    with pytest.raises(ValidationError, match="two nodes"):
        CausalGraph.model_validate_json(json.dumps(graph(edges=edges)))


def test_a_study_is_named_by_its_hash() -> None:
    assert parse(study()).label.startswith("feasibility")
    with pytest.raises(ValidationError, match="SHA-256"):
        parse(study(study_id="cst-20261106-000000000000"))


def test_a_study_cannot_claim_an_effect() -> None:
    with pytest.raises(ValidationError):
        parse(study(effects_estimated=1))
    with pytest.raises(ValidationError):
        parse(study(outcomes_after_treatment_read=True))
    with pytest.raises(ValidationError):
        parse(study(label="causal_effect"))
