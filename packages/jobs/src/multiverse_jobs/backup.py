"""Backup and restore of what cannot be rebuilt (Stage 24, docs/security/backup-restore.md).

The queue, its audit log, and the files of jobs and simulations exist only here. Everything else
in the data folder comes back from git and the immutable raw archive, so it stays out. No secret
is inside: ``.env`` is never read.

SQLite goes through its own backup call, so a queue in use still gives a consistent copy. Every
file is listed with its SHA-256; a restore checks them first and never writes over existing data.
"""

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MANIFEST = "manifest.json"
DATABASE = Path("jobs") / "jobs.sqlite"
SKIPPED_SUFFIXES = (".sqlite", ".sqlite-wal", ".sqlite-shm")
FOLDERS = ("jobs", "simulations")
FORMAT = 1


class BackupError(ValueError):
    """A backup that cannot be trusted, or a restore that would overwrite something."""


@dataclass(frozen=True)
class Manifest:
    created_at: str
    files: dict[str, str]
    jobs: int
    audit_rows: int


def _digest(path: Path) -> str:
    found = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            found.update(block)
    return found.hexdigest()


def _count(path: Path, table: str) -> int:
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        db.close()


def _copy_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    origin = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        origin.backup(copy)
        # One file, so that reading a backup leaves nothing beside it.
        copy.execute("PRAGMA journal_mode=DELETE")
    finally:
        copy.close()
        origin.close()


def _members(data_dir: Path) -> list[Path]:
    found: list[Path] = []
    for folder in FOLDERS:
        root = data_dir / folder
        if root.is_dir():
            found.extend(
                path
                for path in sorted(root.rglob("*"))
                if path.is_file() and not path.name.endswith(SKIPPED_SUFFIXES)
            )
    return found


def create(data_dir: Path, target: Path, moment: datetime) -> Manifest:
    """A new folder with the queue and the files of its jobs; an existing folder is refused."""
    if target.exists():
        raise BackupError(f"{target} exists: a backup never replaces another one")
    if not (data_dir / DATABASE).exists():
        raise BackupError(f"no queue at {data_dir / DATABASE}")
    target.mkdir(parents=True)
    _copy_database(data_dir / DATABASE, target / DATABASE)
    for path in _members(data_dir):
        copied = target / path.relative_to(data_dir)
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, copied)
    files = {
        path.relative_to(target).as_posix(): _digest(path)
        for path in sorted(target.rglob("*"))
        if path.is_file()
    }
    manifest = Manifest(
        created_at=moment.isoformat(),
        files=files,
        jobs=_count(target / DATABASE, "jobs"),
        audit_rows=_count(target / DATABASE, "audit"),
    )
    text = json.dumps({"format": FORMAT, **manifest.__dict__}, indent=1, sort_keys=True)
    (target / MANIFEST).write_text(text, encoding="utf-8")
    return manifest


def verify(target: Path) -> Manifest:
    """Every listed file is there and unchanged, and nothing else was added."""
    path = target / MANIFEST
    if not path.exists():
        raise BackupError(f"no manifest in {target}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("format") != FORMAT:
        raise BackupError(f"unknown backup format {raw.get('format')}")
    manifest = Manifest(raw["created_at"], raw["files"], raw["jobs"], raw["audit_rows"])
    present = {
        item.relative_to(target).as_posix()
        for item in target.rglob("*")
        if item.is_file() and item.name != MANIFEST
    }
    if present != set(manifest.files):
        odd = sorted(present ^ set(manifest.files))
        raise BackupError(f"files differ from the manifest: {', '.join(odd[:5])}")
    for name, expected in manifest.files.items():
        if _digest(target / name) != expected:
            raise BackupError(f"{name} does not match its SHA-256")
    return manifest


def restore(target: Path, data_dir: Path) -> Manifest:
    """Back into a data folder that holds no queue: a restore overwrites nothing."""
    manifest = verify(target)
    if (data_dir / DATABASE).exists():
        raise BackupError(f"{data_dir / DATABASE} exists: restore into an empty folder")
    for name in manifest.files:
        copied = data_dir / name
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target / name, copied)
    return manifest
