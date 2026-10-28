"""Write the intervention catalog as JSON for the web app and the API (Stage 05).

Usage:
    uv run python -m multiverse_contracts.catalog           # write catalog/interventions.json
    uv run python -m multiverse_contracts.catalog --check   # exit 1 if the file is stale
"""

import argparse
import sys
from pathlib import Path

from multiverse_contracts.interventions import CATALOG

# packages/contracts/python/src/multiverse_contracts/catalog.py -> packages/contracts/catalog/
CATALOG_PATH = Path(__file__).resolve().parents[3] / "catalog" / "interventions.json"


def render() -> str:
    return CATALOG.model_dump_json(indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the catalog file is stale")
    args = parser.parse_args(argv)

    expected = render()
    if args.check:
        current = CATALOG_PATH.read_text(encoding="utf-8") if CATALOG_PATH.exists() else ""
        if current != expected:
            print(f"{CATALOG_PATH.name} is stale. Run: npm run contracts:gen", file=sys.stderr)
            return 1
        print(f"{CATALOG_PATH.name} is up to date ({len(CATALOG.interventions)} decision types)")
        return 0

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {CATALOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
