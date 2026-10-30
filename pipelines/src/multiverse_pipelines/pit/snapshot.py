"""Reproducible as-of snapshots and their lineage export.

A snapshot is the panel at one cutoff plus each company's identity at that cutoff,
written as canonical JSON lines (sorted keys, fixed separators, cells in a fixed order).
Its SHA-256 names it: ``pit-<cutoff date>-<first 12 hex digits>``. The same cutoff,
view, window and companies give the same bytes, whatever was filed after the cutoff and
whenever the archive was downloaded. A cutoff after the archive's download time is
refused: a filing accepted in between would be missing. The manifest beside it records
the inputs and versions; it is not hashed, so the build time does not change the name.

Folder ``var/data/pit/snapshots/<snapshot id>/``:

    snapshot.jsonl   header, companies as of the cutoff, cells (the hashed file)
    panel.csv        the cells flattened
    features.csv     trailing-twelve-month and growth features with masks
    lineage.jsonl    each value: source facts, filings, when public, raw file SHA-256
    manifest.json    PitSnapshotManifest
"""

import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from multiverse_contracts.pit import (
    PANEL_SCHEMA_VERSION,
    PIT_POLICY_VERSION,
    CellState,
    EntityAttributeName,
    KnowledgeView,
    PitSnapshotManifest,
    StateCount,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.pit.clock import eastern_date, stamp
from multiverse_pipelines.pit.features import Feature, build_features
from multiverse_pipelines.pit.filings import attribute_as_of
from multiverse_pipelines.pit.panel import PANEL_METRICS, Panel, build_panel
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.cik import cik10

PANEL_COLUMNS: tuple[str, ...] = (
    "cik",
    "calendar_quarter",
    "quarter_end",
    "lag",
    "metric",
    "state",
    "mask",
    "value",
    "unit",
    "currency",
    "fiscal_year",
    "fiscal_period",
    "period_start",
    "period_end",
    "method",
    "concept",
    "accession",
    "known_from",
    "flags",
    "reason",
)


@dataclass(frozen=True)
class Snapshot:
    manifest: PitSnapshotManifest
    panel: Panel
    entities: tuple[dict[str, Any], ...]
    features: tuple[Feature, ...]
    body: bytes


def _line(data: dict[str, Any]) -> bytes:
    return (
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def entities_as_of(
    warehouse: Warehouse, ciks: Iterable[str], cutoff: datetime
) -> list[dict[str, Any]]:
    records = warehouse.attributes()
    found: list[dict[str, Any]] = []
    for cik in sorted({cik10(c) for c in ciks}):
        entity: dict[str, Any] = {"cik": cik}
        for attribute in EntityAttributeName:
            values, reason = attribute_as_of(records, cik, attribute, cutoff)
            entity[attribute.value] = list(values)
            if reason:
                entity[f"{attribute.value}_unknown"] = reason
        index = warehouse.filings(cik)
        gone = index.deregistered(cutoff)
        known = index.known(cutoff)
        entity["status"] = (
            "no_filings_yet" if not known else "deregistration_filed" if gone else "reporting"
        )
        if gone is not None:
            entity["deregistration"] = {
                "form": gone.form,
                "filing_date": gone.filing_date.isoformat(),
            }
        found.append(entity)
    return found


def make_snapshot(
    warehouse: Warehouse,
    ciks: Sequence[str],
    cutoff: datetime,
    *,
    cutoff_label: str,
    created_at: datetime,
    view: KnowledgeView = KnowledgeView.VINTAGE,
    quarters: int = 20,
    metrics: Sequence[str] = PANEL_METRICS,
) -> Snapshot:
    ciks = sorted({cik10(c) for c in ciks})
    inputs = warehouse.inputs(ciks)
    downloaded = min((item.downloaded_at for item in inputs), default=None)
    if downloaded is not None and cutoff > downloaded:
        raise ValueError(
            f"cutoff {cutoff_label} is after the archive was downloaded ({stamp(downloaded)}): "
            "a filing accepted in between is missing, so this snapshot could still change"
        )
    panel = build_panel(warehouse, ciks, cutoff, view=view, quarters=quarters, metrics=metrics)
    entities = entities_as_of(warehouse, ciks, cutoff)
    header = {
        "type": "header",
        "cutoff": stamp(cutoff),
        "view": view.value,
        "quarters": quarters,
        "ciks": ciks,
        "metrics": list(metrics),
        "policy_version": PIT_POLICY_VERSION,
        "panel_schema_version": PANEL_SCHEMA_VERSION,
    }
    parts = [_line(header)]
    parts += [_line({"type": "company", **entity}) for entity in entities]
    parts += [_line({"type": "cell", **cell.model_dump(mode="json")}) for cell in panel.cells]
    body = b"".join(parts)
    digest = hashlib.sha256(body).hexdigest()
    counts = Counter(cell.state for cell in panel.cells)
    manifest = PitSnapshotManifest(
        snapshot_id=f"pit-{eastern_date(cutoff):%Y%m%d}-{digest[:12]}",
        sha256=digest,
        cutoff=cutoff,
        cutoff_label=cutoff_label,
        view=view,
        quarters=quarters,
        ciks=tuple(ciks),
        metrics=tuple(metrics),
        cells=len(panel.cells),
        state_counts=tuple(StateCount(state=s, cells=counts[s]) for s in CellState if counts[s]),
        contracts_version=CONTRACTS_VERSION,
        inputs=tuple(inputs),
        alerts=len(warehouse.alerts(ciks)),
        created_at=created_at,
    )
    return Snapshot(manifest, panel, tuple(entities), tuple(build_features(panel.cells)), body)


def lineage_rows(snapshot: Snapshot, warehouse: Warehouse) -> list[dict[str, Any]]:
    """For every value of the snapshot: where it came from, down to the raw file."""
    raw = {
        item.path.split("/")[2]: item
        for item in warehouse.inputs(snapshot.manifest.ciks)
        if item.path.startswith("sec/companyfacts/")
    }
    rows: list[dict[str, Any]] = []
    for cell in snapshot.panel.cells:
        if not cell.mask:
            continue
        item = snapshot.panel.sources[(cell.cik, cell.calendar_quarter, cell.metric)]
        timing = {t.accession: t for t in item.timings}
        source_file = raw.get(f"CIK{cell.cik}")
        rows.append(
            {
                "cik": cell.cik,
                "calendar_quarter": cell.calendar_quarter,
                "metric": cell.metric,
                "value": cell.value,
                "view": snapshot.manifest.view.value,
                "method": cell.method.value if cell.method else None,
                "formula": item.value.formula,
                "known_from": stamp(item.known_from),
                "change": item.change.value,
                "sources": [
                    {
                        "concept": s.concept,
                        "period_start": s.period_start.isoformat() if s.period_start else None,
                        "period_end": s.period_end.isoformat(),
                        "value": s.value,
                        "sign": s.sign,
                        "accession": s.accession,
                        "form": s.form,
                        "filed": s.filed.isoformat(),
                        "public_at": stamp(timing[s.accession].known_at),
                        "time_precision": timing[s.accession].precision.value,
                        "filing_url": filing_url(cell.cik, s.accession),
                    }
                    for s in item.value.sources
                ],
                "raw_file": None
                if source_file is None
                else {
                    "path": source_file.path,
                    "sha256": source_file.sha256,
                    "url": source_file.url,
                    "downloaded_at": stamp(source_file.downloaded_at),
                },
            }
        )
    return rows


def filing_url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"


def panel_csv(snapshot: Snapshot) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PANEL_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for cell in snapshot.panel.cells:
        data = cell.model_dump(mode="json")
        row = {name: "" if data.get(name) is None else str(data[name]) for name in PANEL_COLUMNS}
        row["flags"] = ";".join(cell.flags)
        row["mask"] = "1" if cell.mask else "0"
        writer.writerow(row)
    return buffer.getvalue()


def features_csv(features: Sequence[Feature]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("cik", "calendar_quarter", "lag", "feature", "value", "mask", "reason"))
    for f in features:
        value = "" if f.value is None else format(f.value, "f")
        writer.writerow(
            (f.cik, f.calendar_quarter, f.lag, f.name, value, int(f.mask), f.reason or "")
        )
    return buffer.getvalue()


def write_snapshot(snapshot: Snapshot, warehouse: Warehouse, root: Path) -> Path:
    folder = root / snapshot.manifest.snapshot_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "snapshot.jsonl").write_bytes(snapshot.body)
    (folder / "panel.csv").write_text(panel_csv(snapshot), encoding="utf-8", newline="")
    (folder / "features.csv").write_text(
        features_csv(snapshot.features), encoding="utf-8", newline=""
    )
    lineage = b"".join(_line(row) for row in lineage_rows(snapshot, warehouse))
    (folder / "lineage.jsonl").write_bytes(lineage)
    manifest = json.dumps(snapshot.manifest.model_dump(mode="json"), indent=2, ensure_ascii=False)
    (folder / "manifest.json").write_text(manifest + "\n", encoding="utf-8")
    return folder
