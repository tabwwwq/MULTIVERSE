"""Immutable raw archive with an append-only metadata index (ADR-0017).

Layout under the raw root (``var/raw`` by default, never committed):

    sec/<dataset>/<key>/<sha256>.<json|zip>   read-only files, named by their SHA-256
    sec/index.jsonl                           one RawObject per stored file
    sec/runs/<run_id>.json                    one RunManifest per command
    sec/tmp/*.part                            unfinished downloads, removed at the next start

A file is moved into place only after it was fully received and validated, so an
interrupted download leaves at most a ``.part`` file. The same bytes are never stored
twice; a changed file becomes a new object next to the old one.
"""

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from multiverse_pipelines.sec.errors import ArchiveCorruptedError, TooLargeError
from multiverse_pipelines.sec.models import Outcome, RawObject, RunManifest

CHECKED_OUTCOMES = frozenset({Outcome.NEW, Outcome.UNCHANGED, Outcome.NOT_MODIFIED})
Describe = Callable[[str, int, str], RawObject]


def sha256_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256")
    return digest.hexdigest(), path.stat().st_size


def make_read_only(path: Path) -> None:
    path.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)


@dataclass
class VerifyReport:
    checked: int = 0
    problems: list[str] = field(default_factory=list)


class RawArchive:
    def __init__(self, root: Path, *, budget_bytes: int, source_dir: str = "sec") -> None:
        self.root = root
        self.base = root / source_dir
        self.tmp_dir = self.base / "tmp"
        self.runs_dir = self.base / "runs"
        self.index_path = self.base / "index.jsonl"
        self.budget_bytes = budget_bytes

    def objects(self) -> list[RawObject]:
        if not self.index_path.exists():
            return []
        rows: list[RawObject] = []
        with self.index_path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    rows.append(RawObject.model_validate_json(line))
                except ValidationError as exc:
                    raise ArchiveCorruptedError(f"{self.index_path} line {number}: {exc}") from exc
        return rows

    def latest(self, dataset_id: str, key: str) -> RawObject | None:
        rows = [o for o in self.objects() if o.dataset_id == dataset_id and o.key == key]
        return max(rows, key=lambda o: o.downloaded_at, default=None)

    def usage_bytes(self) -> int:
        return sum(o.size_bytes for o in self.objects())

    def remaining_bytes(self) -> int:
        return max(self.budget_bytes - self.usage_bytes(), 0)

    def clean_partials(self) -> int:
        if not self.tmp_dir.exists():
            return 0
        removed = 0
        for part in self.tmp_dir.glob("*.part"):
            part.unlink()
            removed += 1
        return removed

    def store(
        self, tmp_path: Path, *, dataset_id: str, key: str, file_format: str, describe: Describe
    ) -> tuple[RawObject, bool]:
        """Move a validated download into place; ``False`` when the same bytes are stored."""
        sha, size = sha256_file(tmp_path)
        relative = f"{dataset_id.removeprefix('sec-')}/{key}/{sha}.{file_format}"
        dest = self.base / relative
        known = next(
            (
                o
                for o in self.objects()
                if (o.dataset_id, o.key, o.sha256) == (dataset_id, key, sha)
            ),
            None,
        )
        if known is not None:
            tmp_path.unlink()
            if not dest.exists() or sha256_file(dest)[0] != sha:
                raise ArchiveCorruptedError(f"{dest} no longer matches its checksum; run verify")
            return known, False
        if size > self.remaining_bytes():
            tmp_path.unlink()
            raise TooLargeError(
                f"{size} bytes do not fit in the {self.remaining_bytes()} bytes left"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            # Left by a run that stopped between the move and the index line: adopt it.
            tmp_path.unlink()
            if sha256_file(dest)[0] != sha:
                raise ArchiveCorruptedError(f"{dest} no longer matches its checksum; run verify")
        else:
            os.replace(tmp_path, dest)
            make_read_only(dest)
        row = describe(sha, size, f"{self.base.name}/{relative}")
        self._append(row)
        return row, True

    def _append(self, row: RawObject) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(row.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def save_manifest(self, manifest: RunManifest) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / f"{manifest.run_id}.json"
        part = path.with_suffix(".json.part")
        part.write_bytes(manifest.model_dump_json(indent=2).encode("utf-8") + b"\n")
        os.replace(part, path)
        make_read_only(path)
        return path

    def manifests(self) -> list[RunManifest]:
        if not self.runs_dir.exists():
            return []
        paths = sorted(self.runs_dir.glob("*.json"))
        return [RunManifest.model_validate_json(p.read_bytes()) for p in paths]

    def last_checked(self) -> dict[tuple[str, str], datetime]:
        """When the source last confirmed each file, from the manifests of earlier runs."""
        seen: dict[tuple[str, str], datetime] = {}
        for manifest in self.manifests():
            for record in manifest.records:
                if record.outcome in CHECKED_OUTCOMES:
                    slot = (record.dataset_id, record.key)
                    if slot not in seen or record.checked_at > seen[slot]:
                        seen[slot] = record.checked_at
        return seen

    def verify(self) -> VerifyReport:
        """Re-hash every stored file and look for files the index does not know."""
        report = VerifyReport()
        known: set[Path] = set()
        for row in self.objects():
            path = self.root / row.path
            known.add(path.resolve())
            report.checked += 1
            if not path.exists():
                report.problems.append(f"missing: {row.path}")
                continue
            sha, size = sha256_file(path)
            if (sha, size) != (row.sha256, row.size_bytes):
                report.problems.append(f"checksum or size changed: {row.path}")
            if os.access(path, os.W_OK):
                report.problems.append(f"writable, should be read-only: {row.path}")
        skip = {self.tmp_dir.resolve(), self.runs_dir.resolve()}
        # Sorted: directory order differs between file systems; the report must not.
        for path in sorted(self.base.rglob("*")):
            if not path.is_file() or path == self.index_path:
                continue
            if any(parent in skip for parent in path.resolve().parents):
                continue
            if path.resolve() not in known:
                report.problems.append(
                    f"not in the index: {path.relative_to(self.root).as_posix()}"
                )
        return report
