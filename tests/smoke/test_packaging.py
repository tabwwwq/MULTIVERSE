"""What the public repository may hold (Stage 24, docs/12, prompt 24).

Public access to a source is not a licence to republish it. These tests read what git tracks,
so a raw file, a database, a checkpoint or a new data folder fails before it can be pushed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_SUFFIXES = {
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".duckdb",
    ".parquet",
    ".pt",
    ".pth",
    ".ckpt",
    ".safetensors",
    ".pkl",
    ".pickle",
    ".joblib",
    ".npz",
    ".npy",
    ".pem",
    ".key",
    ".pfx",
}
REVIEWED_DATA = {
    "causal": "derived study, no raw source text",
    "events": "48 events with short notes and links to public SEC filings",
    "protocols": "our own protocols",
    "reconciliation": "10 manual checks of public filings",
    "schemas": "documentation",
    "simulation": "holds values derived from FRED: open block, license inventory",
    "universe": "identifiers of companies from public SEC data",
    "valuation": "holds values derived from FRED: open block, license inventory",
}
LARGEST_FILE = 3_000_000
GIT = shutil.which("git")


def tracked() -> list[str]:
    if GIT is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("this test reads what git tracks")
    found = subprocess.run([GIT, "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True)
    return [name for name in found.stdout.decode().split("\0") if name]


def test_git_tracks_this_repository() -> None:
    assert "README.md" in tracked()


def test_no_archive_database_checkpoint_or_key_is_tracked() -> None:
    bad = [name for name in tracked() if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES]
    assert bad == []


def test_nothing_local_is_tracked() -> None:
    bad = [
        name
        for name in tracked()
        if name.startswith(("var/", ".venv/", "node_modules/"))
        or (Path(name).name.startswith(".env") and name != ".env.example")
    ]
    assert bad == []


def test_every_data_folder_was_reviewed() -> None:
    folders = {name.split("/")[1] for name in tracked() if name.startswith("data/")}
    assert folders <= set(REVIEWED_DATA), "review the licence of a new data folder first"


def test_no_tracked_file_is_large_enough_to_be_a_dataset() -> None:
    bad = [
        name
        for name in tracked()
        if (REPO_ROOT / name).exists() and (REPO_ROOT / name).stat().st_size > LARGEST_FILE
    ]
    assert bad == []


def test_paid_sources_stay_out_of_the_catalog_as_data() -> None:
    catalog = json.loads(
        (REPO_ROOT / "packages/contracts/catalog/sources.json").read_text(encoding="utf-8")
    )
    assert catalog["automatic_downloads"] == "disabled"
    assert {need["status"] for need in catalog["licensed_needs"]} == {"not_selected"}


def test_the_open_blocks_of_fred_stay_in_the_catalog() -> None:
    catalog = json.loads(
        (REPO_ROOT / "packages/contracts/catalog/sources.json").read_text(encoding="utf-8")
    )
    fred = next(s for s in catalog["sources"] if s["source_id"] == "fred-alfred")
    assert {block["use"] for block in fred["blocks"]} == {
        "machine_learning",
        "archive",
        "republication",
    }
