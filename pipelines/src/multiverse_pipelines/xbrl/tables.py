"""Standardized tables of normalized values, their schema and a coverage data card.

Output folder (``var/data/normalized/sec`` by default, never committed):

    values.jsonl    one NormalizedValue per line, full lineage (the reference format)
    values.csv      the same rows flattened for spreadsheets and quick queries
    schema.json     JSON Schema of NormalizedValue (contracts)
    coverage.json   per company and metric: valid quarters in the last 8, 20 and 40
    coverage.md     the same as a data card, with concepts and methods used (DATA-05)
    manifest.json   inputs (raw files and their SHA-256), versions, row counts
"""

import csv
import io
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from multiverse_contracts.normalized import FiscalPeriod, NormalizedValue, Revision
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.xbrl.concepts import CALCULATED, METRICS

CSV_COLUMNS = (
    "cik",
    "metric",
    "fiscal_year",
    "fiscal_period",
    "period_kind",
    "period_start",
    "period_end",
    "revision",
    "value",
    "unit",
    "currency",
    "missing_reason",
    "concept",
    "method",
    "formula",
    "accession",
    "filed",
    "original_value",
    "quality",
    "flags",
    "sources",
    "alternatives",
)
WINDOWS = (8, 20, 40)
QUARTERS = (FiscalPeriod.Q1, FiscalPeriod.Q2, FiscalPeriod.Q3, FiscalPeriod.Q4)
METRIC_NAMES = tuple(spec.metric for spec in METRICS) + tuple(spec.metric for spec in CALCULATED)


def csv_row(row: NormalizedValue) -> dict[str, str]:
    data = row.model_dump(mode="json")
    flat = {name: "" if data.get(name) is None else str(data[name]) for name in CSV_COLUMNS}
    flat["flags"] = ";".join(row.flags)
    flat["sources"] = " ".join(
        f"{'+' if s.sign > 0 else '-'}{s.concept}[{s.period_start or ''}..{s.period_end}]"
        f"={s.value}@{s.accession}/{s.filed}"
        for s in row.sources
    )
    flat["alternatives"] = " ".join(
        f"{a.concept}={a.value}(diff {a.difference})" for a in row.alternatives
    )
    return flat


def write_csv(rows: Iterable[NormalizedValue], path: Path) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(csv_row(row))
    path.write_bytes(buffer.getvalue().encode("utf-8"))


def write_jsonl(rows: Iterable[NormalizedValue], path: Path) -> None:
    path.write_bytes("".join(row.model_dump_json() + "\n" for row in rows).encode("utf-8"))


def read_jsonl(path: Path) -> list[NormalizedValue]:
    with path.open(encoding="utf-8") as handle:
        return [NormalizedValue.model_validate_json(line) for line in handle if line.strip()]


@dataclass
class MetricCoverage:
    metric: str
    valid: dict[int, int] = field(default_factory=dict)
    total_valid: int = 0
    first: str | None = None
    concepts: Counter[str] = field(default_factory=Counter)
    methods: Counter[str] = field(default_factory=Counter)
    flags: Counter[str] = field(default_factory=Counter)


def coverage(rows: Sequence[NormalizedValue]) -> dict[str, dict[str, MetricCoverage]]:
    """Valid quarters of the latest revision, counted back from each company's last quarter."""
    by_company: dict[str, list[NormalizedValue]] = {}
    for row in rows:
        if row.revision is Revision.LATEST and row.fiscal_period in QUARTERS:
            by_company.setdefault(row.cik, []).append(row)
    result: dict[str, dict[str, MetricCoverage]] = {}
    for cik, items in by_company.items():
        order = sorted({(r.fiscal_year, QUARTERS.index(r.fiscal_period)) for r in items})
        with_value = [(r.fiscal_year, QUARTERS.index(r.fiscal_period)) for r in items if r.value]
        last = max(with_value) if with_value else order[-1]
        timeline = [slot for slot in order if slot <= last]
        metrics: dict[str, MetricCoverage] = {}
        for name in METRIC_NAMES:
            entry = MetricCoverage(name)
            present = {
                (r.fiscal_year, QUARTERS.index(r.fiscal_period)): r
                for r in items
                if r.metric == name and r.value is not None
            }
            for window in WINDOWS:
                entry.valid[window] = sum(slot in present for slot in timeline[-window:])
            entry.total_valid = len(present)
            if present:
                year, quarter = min(present)
                entry.first = f"{year} {QUARTERS[quarter].value}"
            for row in present.values():
                entry.concepts[row.concept or (row.formula or "")] += 1
                entry.methods[row.method.value if row.method else ""] += 1
                entry.flags.update(row.flags)
            metrics[name] = entry
        result[cik] = metrics
    return result


def coverage_json(table: Mapping[str, Mapping[str, MetricCoverage]]) -> dict[str, object]:
    return {
        cik: {
            name: {
                "valid_quarters": {str(w): entry.valid[w] for w in WINDOWS},
                "total_valid_quarters": entry.total_valid,
                "first_quarter": entry.first,
                "concepts": dict(entry.concepts.most_common()),
                "methods": dict(entry.methods.most_common()),
                "flags": dict(entry.flags.most_common()),
            }
            for name, entry in metrics.items()
        }
        for cik, metrics in table.items()
    }


def coverage_markdown(
    table: Mapping[str, Mapping[str, MetricCoverage]], names: Mapping[str, str]
) -> str:
    """Data card: valid quarters in the last 8 / 20 / 40, latest revision."""
    lines = [
        "# Coverage of normalized SEC values",
        "",
        "Valid quarters of the latest revision in the last 8 / 20 / 40 fiscal quarters of each",
        "company. A quarter is valid when it has a value; missing values are never zero.",
        "",
        "| Company | " + " | ".join(METRIC_NAMES) + " |",
        "|---|" + "---|" * len(METRIC_NAMES),
    ]
    for cik, metrics in table.items():
        cells = " | ".join(
            "/".join(str(metrics[name].valid[w]) for w in WINDOWS) for name in METRIC_NAMES
        )
        lines.append(f"| {names.get(cik, cik)} | {cells} |")
    lines += ["", "## Concepts used per metric", ""]
    for cik, metrics in table.items():
        lines.append(f"### {names.get(cik, cik)}")
        lines.append("")
        for name in METRIC_NAMES:
            entry = metrics[name]
            used = ", ".join(f"{c} ({n})" for c, n in entry.concepts.most_common()) or "none"
            methods = ", ".join(f"{m} {n}" for m, n in entry.methods.most_common())
            lines.append(f"- **{name}**: {used}" + (f"; {methods}" if methods else ""))
        lines.append("")
    return "\n".join(lines)


def write_outputs(
    rows: Sequence[NormalizedValue],
    folder: Path,
    *,
    inputs: Sequence[Mapping[str, object]],
    names: Mapping[str, str],
) -> dict[str, int]:
    folder.mkdir(parents=True, exist_ok=True)
    write_jsonl(rows, folder / "values.jsonl")
    write_csv(rows, folder / "values.csv")
    schema = NormalizedValue.model_json_schema(mode="serialization")
    (folder / "schema.json").write_bytes(json.dumps(schema, indent=2).encode("utf-8") + b"\n")
    table = coverage(rows)
    (folder / "coverage.json").write_bytes(
        json.dumps(coverage_json(table), indent=2).encode("utf-8") + b"\n"
    )
    (folder / "coverage.md").write_bytes(coverage_markdown(table, names).encode("utf-8"))
    counts = {
        "rows": len(rows),
        "values": sum(r.value is not None for r in rows),
        "missing": sum(r.value is None for r in rows),
        "blocking": sum(r.quality == "blocking" for r in rows),
        "restated": sum("restated" in r.flags for r in rows),
    }
    manifest = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "contracts_version": CONTRACTS_VERSION,
        "inputs": list(inputs),
        "counts": counts,
    }
    (folder / "manifest.json").write_bytes(json.dumps(manifest, indent=2).encode("utf-8") + b"\n")
    return counts
