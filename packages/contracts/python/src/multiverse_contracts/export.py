"""Export all contracts as one JSON Schema document (ADR-0008).

Usage:
    uv run python -m multiverse_contracts.export           # write the schema file
    uv run python -m multiverse_contracts.export --check   # exit 1 if the file is stale
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from multiverse_contracts.companies import CompanyDossier
from multiverse_contracts.decisions import ScenarioDraft
from multiverse_contracts.interventions import InterventionCatalog
from multiverse_contracts.macro import MacroCell, MacroObservation, MacroSeries
from multiverse_contracts.manifest import ReproducibilityManifest
from multiverse_contracts.metrics import MetricValue
from multiverse_contracts.normalized import NormalizedValue
from multiverse_contracts.notebook import NotebookExport
from multiverse_contracts.pit import ChronologyAlert, PanelCell, PitSnapshotManifest, PitValue
from multiverse_contracts.quality import GateManifest
from multiverse_contracts.results import ScenarioResult
from multiverse_contracts.sources import SourceCatalog
from multiverse_contracts.universe import UniverseManifest
from multiverse_contracts.version import CONTRACTS_VERSION

# packages/contracts/python/src/multiverse_contracts/export.py -> packages/contracts/schemas/
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "contracts.schema.json"

# Top-level models. Nested models and enums are exported automatically through $defs.
EXPORTED_MODELS: tuple[type[BaseModel], ...] = (
    MetricValue,
    ReproducibilityManifest,
    CompanyDossier,
    ScenarioDraft,
    InterventionCatalog,
    ScenarioResult,
    NotebookExport,
    SourceCatalog,
    NormalizedValue,
    PitValue,
    PanelCell,
    ChronologyAlert,
    PitSnapshotManifest,
    MacroSeries,
    MacroObservation,
    MacroCell,
    GateManifest,
    UniverseManifest,
)


def _strip_property_titles(node: object) -> None:
    """Drop per-field titles: TypeScript generation would turn each one into a separate type."""
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            for prop in properties.values():
                if isinstance(prop, dict):
                    prop.pop("title", None)
        for value in node.values():
            _strip_property_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_property_titles(item)


def build_schema() -> dict[str, object]:
    # Serialization mode: the schema describes what services send, which is what the web
    # app consumes. Fields with defaults are therefore always present (ADR-0008).
    _, schema = models_json_schema([(model, "serialization") for model in EXPORTED_MODELS])
    _strip_property_titles(schema)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:multiverse:contracts:{CONTRACTS_VERSION}",
        "title": "MultiverseContracts",
        "description": "Generated from packages/contracts/python. Do not edit by hand.",
        "x-contracts-version": CONTRACTS_VERSION,
        **schema,
    }


def render() -> str:
    return json.dumps(build_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the schema file is stale")
    args = parser.parse_args(argv)

    expected = render()
    if args.check:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current != expected:
            print(f"{SCHEMA_PATH.name} is stale. Run: npm run contracts:gen", file=sys.stderr)
            return 1
        print(f"{SCHEMA_PATH.name} is up to date (contracts {CONTRACTS_VERSION})")
        return 0

    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
