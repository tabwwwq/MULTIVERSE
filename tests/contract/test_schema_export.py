"""The committed JSON Schema is exactly what the Python contracts produce (ADR-0008)."""

import json

from multiverse_contracts import CONTRACTS_VERSION
from multiverse_contracts.export import SCHEMA_PATH, build_schema, render


def test_committed_schema_matches_python_contracts() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render(), (
        "contracts.schema.json is stale. Run: npm run contracts:gen"
    )


def test_export_is_deterministic() -> None:
    assert render() == render()


def test_schema_carries_contracts_version_and_all_models() -> None:
    schema = json.loads(render())

    assert schema["x-contracts-version"] == CONTRACTS_VERSION
    assert {"MetricValue", "ReproducibilityManifest", "Quantity", "ValueKind"} <= set(
        schema["$defs"]
    )


def test_property_titles_are_not_exported() -> None:
    defs = build_schema()["$defs"]
    assert isinstance(defs, dict)

    for definition in defs.values():
        for prop in definition.get("properties", {}).values():
            assert "title" not in prop
