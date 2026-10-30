"""The joined panel: company cells of a PIT snapshot plus macro cells, with provenance.

Folder ``var/data/macro/joined/<id>/`` (``joined-synthetic`` when the macro store is the
synthetic one), never committed:

    joined.csv          one row per company quarter and feature, financial and macro
    macro_cells.jsonl   every macro cell with its input observations and availability
    manifest.json       cutoff, the PIT snapshot it extends, counts, synthetic flag, hash

The id is ``join-<cutoff date>-<12 hex>`` of the SHA-256 over the PIT snapshot's bytes
and the canonical macro cells: the same cutoff and inputs give the same id.
"""

import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from multiverse_contracts.macro import MacroCell
from multiverse_pipelines.pit.clock import eastern_date, stamp
from multiverse_pipelines.pit.snapshot import Snapshot

COLUMNS: tuple[str, ...] = (
    "cik",
    "calendar_quarter",
    "lag",
    "kind",
    "name",
    "value",
    "mask",
    "state",
    "available_from",
    "synthetic",
    "provenance",
)


@dataclass(frozen=True)
class Joined:
    join_id: str
    sha256: str
    body: bytes
    rows: list[dict[str, str]]
    manifest: dict[str, Any]


def _line(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def make_joined(
    snapshot: Snapshot, cells: Sequence[MacroCell], *, synthetic_store: bool, created_at: datetime
) -> Joined:
    ordered = sorted(cells, key=lambda c: (c.cik, c.calendar_quarter, c.feature))
    macro_body = b"".join(_line(c.model_dump(mode="json")) for c in ordered)
    digest = hashlib.sha256(snapshot.body + macro_body).hexdigest()
    cutoff = snapshot.manifest.cutoff
    join_id = f"join-{eastern_date(cutoff):%Y%m%d}-{digest[:12]}"
    rows: list[dict[str, str]] = []
    for panel_cell in snapshot.panel.cells:
        rows.append(
            {
                "cik": panel_cell.cik,
                "calendar_quarter": panel_cell.calendar_quarter,
                "lag": str(panel_cell.lag),
                "kind": "financial",
                "name": panel_cell.metric,
                "value": panel_cell.value or "",
                "mask": "1" if panel_cell.mask else "0",
                "state": panel_cell.state.value,
                "available_from": stamp(panel_cell.known_from) if panel_cell.known_from else "",
                "synthetic": "0",
                "provenance": f"SEC {panel_cell.accession}"
                if panel_cell.accession
                else (panel_cell.reason or ""),
            }
        )
    for cell in ordered:
        latest = max((i.available_from for i in cell.inputs), default=None)
        provenance = (
            "; ".join(
                f"{cell.series_id} {i.period_start} published {stamp(i.available_from)} "
                f"({i.basis.value})"
                for i in cell.inputs
            )
            if cell.inputs
            else cell.reason or ""
        )
        rows.append(
            {
                "cik": cell.cik,
                "calendar_quarter": cell.calendar_quarter,
                "lag": str(cell.lag),
                "kind": "macro",
                "name": cell.feature,
                "value": cell.value or "",
                "mask": "1" if cell.mask else "0",
                "state": cell.state.value,
                "available_from": stamp(latest) if latest else "",
                "synthetic": "1" if cell.synthetic else "0",
                "provenance": provenance,
            }
        )
    by_feature: dict[str, Counter[str]] = {}
    for cell in ordered:
        by_feature.setdefault(cell.feature, Counter())[cell.state.value] += 1
    manifest = {
        "join_id": join_id,
        "sha256": digest,
        "cutoff": stamp(cutoff),
        "cutoff_label": snapshot.manifest.cutoff_label,
        "pit_snapshot_id": snapshot.manifest.snapshot_id,
        "quarters": snapshot.manifest.quarters,
        "companies": len(snapshot.manifest.ciks),
        "financial_cells": len(snapshot.panel.cells),
        "macro_cells": len(ordered),
        "macro_states": {k: dict(v) for k, v in sorted(by_feature.items())},
        "synthetic_macro": synthetic_store,
        "created_at": stamp(created_at),
    }
    return Joined(join_id, digest, snapshot.body + macro_body, rows, manifest)


def write_joined(joined: Joined, cells: Sequence[MacroCell], root: Path) -> Path:
    folder = root / joined.join_id
    folder.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(joined.rows)
    (folder / "joined.csv").write_text(buffer.getvalue(), encoding="utf-8", newline="")
    ordered = sorted(cells, key=lambda c: (c.cik, c.calendar_quarter, c.feature))
    (folder / "macro_cells.jsonl").write_bytes(
        b"".join(_line(c.model_dump(mode="json")) for c in ordered)
    )
    (folder / "manifest.json").write_text(
        json.dumps(joined.manifest, indent=2) + "\n", encoding="utf-8"
    )
    return folder
