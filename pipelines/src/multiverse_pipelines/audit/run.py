"""Gate B run: every check, the example counts, the manifest and the data card.

Inputs are local: the PIT warehouse and raw archive of the SEC sample, the macro stores,
and the manual reconciliation file in ``data/reconciliation/``. The leakage proof
rebuilds the warehouse from only what was public at several cutoffs and compares the
snapshots, and does the same for the macro join.
"""

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from multiverse_contracts.normalized import FiscalPeriod
from multiverse_contracts.pit import MASKED_STATES, KnowledgeView
from multiverse_contracts.quality import (
    CheckStatus,
    CompanyDecision,
    ExampleCount,
    GateCheck,
    GateManifest,
    GateVerdict,
    Measure,
)
from multiverse_contracts.sources import CompanyCandidate
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.audit.checks import CHECKS, AuditData, load
from multiverse_pipelines.audit.examples import Example, count_examples, examples_hash
from multiverse_pipelines.macro.cli import load_synthetic
from multiverse_pipelines.macro.join import macro_join
from multiverse_pipelines.macro.registry import SERIES
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.build import build_warehouse, load_inputs
from multiverse_pipelines.pit.clock import eastern_date, parse_cutoff
from multiverse_pipelines.pit.panel import PANEL_METRICS, build_panel, quarter_ends
from multiverse_pipelines.pit.snapshot import make_snapshot
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_pipelines.sec.archive import RawArchive

MIN_COMPANIES = 30
MIN_EXAMPLES = 1000
MIN_QUARTERS = 12
TARGET = "revenue"
FIRST_ORIGIN = date(2010, 3, 31)
FIRST_QUARTER = date(2009, 9, 30)


@dataclass
class GateResult:
    manifest: GateManifest
    data: AuditData
    examples: list[Example]
    usability: dict[str, list[str]]


def leakage_check(
    archive: RawArchive,
    warehouse: Warehouse,
    ciks: Sequence[str],
    cutoffs: Sequence[str],
    synthetic: MacroStore | None,
    now: datetime,
    workers: int,
) -> GateCheck:
    findings: list[str] = []
    measures: dict[str, str] = {}
    for label in cutoffs:
        cutoff = parse_cutoff(label)
        options: dict[str, Any] = {"cutoff_label": label, "created_at": now, "quarters": 20}
        full = make_snapshot(warehouse, ciks, cutoff, **options)
        then = build_warehouse(archive, ciks, None, built_at=now, known_by=cutoff, workers=workers)
        past = make_snapshot(then, ciks, cutoff, **options)
        then.close()
        same = full.body == past.body
        measures[f"PIT {label}"] = (
            f"{full.manifest.snapshot_id} {'identical' if same else 'DIFFERENT'}"
        )
        if not same:
            findings.append(f"PIT snapshot at {label} changes when later filings are added")
        if synthetic is not None:
            store_then = load_synthetic(None, eastern_date(cutoff), now)
            a = macro_join(full.panel.cells, synthetic, SERIES, cutoff, unavailable={})
            b = macro_join(full.panel.cells, store_then, SERIES, cutoff, unavailable={})
            store_then.close()
            measures[f"macro join {label} (synthetic)"] = "identical" if a == b else "DIFFERENT"
            if a != b:
                findings.append(f"macro join at {label} changes when later releases are added")
    return GateCheck(
        check_id="leakage",
        title="Leakage proof",
        status=CheckStatus.PASS if not findings else CheckStatus.FAIL,
        summary="rebuilt from only what was public at each cutoff, the snapshots and joins are "
        "byte for byte the ones built from everything archived",
        measures=tuple(Measure(name=k, value=v) for k, v in measures.items()),
        findings=tuple(findings),
    )


def reconciliation_check(warehouse: Warehouse, path: Path, data_cutoff: datetime) -> GateCheck:
    if not path.exists():
        return GateCheck(
            check_id="manual_reconciliation",
            title="Manual reconciliation with SEC originals",
            status=CheckStatus.BLOCKED,
            summary="no reconciliation file",
            findings=(f"{path} is missing",),
        )
    entries = json.loads(path.read_text(encoding="utf-8"))["reconciliations"]
    findings: list[str] = []
    matched = 0
    for entry in entries:
        rows = warehouse.as_of(
            entry["cik"],
            data_cutoff,
            view=KnowledgeView(entry["view"]),
            metric=entry["metric"],
            fiscal_year=entry["fiscal_year"],
            fiscal_period=FiscalPeriod(entry["fiscal_period"]),
        )
        found = rows[0].value.value if rows else None
        expected = Decimal(entry["expected"])
        ok = found is not None and Decimal(found) == expected
        matched += ok
        label = (
            f"{entry['company']} {entry['metric']} FY{entry['fiscal_year']} "
            f"{entry['fiscal_period']}"
        )
        verdict = "match" if ok else "MISMATCH"
        findings.append(f"{label}: filings {expected}, MULTIVERSE {found}: {verdict}")
    status = (
        CheckStatus.BLOCKED
        if len(entries) < 10
        else CheckStatus.PASS
        if matched == len(entries)
        else CheckStatus.FAIL
    )
    return GateCheck(
        check_id="manual_reconciliation",
        title="Manual reconciliation with SEC originals",
        status=status,
        summary=f"{matched} of {len(entries)} derived amounts equal the figures read from the "
        "original filings on sec.gov",
        measures=(Measure(name="matched", value=f"{matched} of {len(entries)}"),),
        findings=tuple(findings),
    )


def sample_size_check(counts: Sequence[ExampleCount], usable: int) -> GateCheck:
    main = next(c for c in counts if c.history_quarters == 12 and c.horizon_quarters == 4)
    enough = usable >= MIN_COMPANIES and main.examples >= MIN_EXAMPLES
    return GateCheck(
        check_id="sample_size",
        title="Usable sample size",
        status=CheckStatus.PASS if enough else CheckStatus.BLOCKED,
        summary=f"{usable} companies with at least {MIN_QUARTERS} revenue quarters and "
        f"{main.examples} examples at 12 quarters of history and a 4-quarter horizon; Gate B "
        f"asks for at least {MIN_COMPANIES} companies and {MIN_EXAMPLES} such examples",
        measures=(
            Measure(name="usable companies", value=str(usable)),
            Measure(name="examples (H=12, h=4)", value=str(main.examples)),
        ),
        findings=()
        if enough
        else (
            "the SEC sample of decision D-09 holds 10 companies; the full universe needs the "
            "bulk files of decision D-10",
        ),
    )


def macro_check(real: MacroStore | None) -> GateCheck:
    observations = 0
    if real is not None:
        observations = real.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    return GateCheck(
        check_id="macro_data",
        title="Macro data",
        status=CheckStatus.PASS if observations else CheckStatus.BLOCKED,
        summary="real macro series in the store"
        if observations
        else "no real macro values: the FRED key (D-11) and the ECB / World Bank decision "
        "(D-12) are pending; only the synthetic store exists",
        measures=(Measure(name="real macro observations", value=str(observations)),),
    )


def bankruptcy_filings(
    archive: RawArchive, ciks: Sequence[str], names: dict[str, str]
) -> list[str]:
    found = []
    for cik in ciks:
        inputs = load_inputs(archive, cik)
        for table in [inputs.submissions["filings"]["recent"], *inputs.pages]:
            column = table.get("items") or [""] * len(table["form"])
            for form, items, filed in zip(table["form"], column, table["filingDate"], strict=True):
                if form.startswith("8-K") and "1.03" in (items or "").split(","):
                    found.append(f"{names.get(cik, cik)}: 8-K item 1.03 filed {filed}")
    return found


def usability(data: AuditData) -> dict[str, list[str]]:
    """Per metric, the companies with at least MIN_QUARTERS values in the full panel."""
    counts: Counter[tuple[str, str]] = Counter(
        (c.metric, c.cik) for c in data.panel.cells if c.state in MASKED_STATES
    )
    return {
        metric: sorted(cik for cik in data.ciks if counts[(metric, cik)] >= MIN_QUARTERS)
        for metric in PANEL_METRICS
    }


def decisions(data: AuditData, usable: dict[str, list[str]]) -> list[CompanyDecision]:
    found = []
    for cik in data.ciks:
        reasons: list[str] = []
        include = cik in usable[TARGET]
        if not include:
            reasons.append(f"fewer than {MIN_QUARTERS} revenue quarters")
        gone = data.warehouse.filings(cik).deregistered(data.data_cutoff)
        if gone is not None:
            reasons.append(f"deregistered ({gone.form} {gone.filing_date}): no origins after it")
        missing = [m for m, ciks in usable.items() if cik not in ciks]
        if missing:
            reasons.append("too few quarters for: " + ", ".join(missing))
        found.append(
            CompanyDecision(cik=cik, name=data.name(cik), include=include, reasons=tuple(reasons))
        )
    return found


def run_gate(
    *,
    warehouse: Warehouse,
    archive: RawArchive,
    ciks: Sequence[str],
    names: dict[str, str],
    candidates: dict[str, CompanyCandidate],
    data_cutoff_label: str,
    reconciliation: Path,
    real_macro: MacroStore | None,
    synthetic_macro: MacroStore | None,
    leakage_cutoffs: Sequence[str],
    now: datetime,
    workers: int = 1,
) -> GateResult:
    data_cutoff = parse_cutoff(data_cutoff_label)
    # Every calendar quarter since the first XBRL filings (mid 2009).
    quarters = sum(1 for end in quarter_ends(eastern_date(data_cutoff), 80) if end >= FIRST_QUARTER)
    snapshot = make_snapshot(
        warehouse,
        ciks,
        data_cutoff,
        cutoff_label=data_cutoff_label,
        created_at=now,
        quarters=quarters,
    )
    panel = build_panel(warehouse, ciks, data_cutoff, quarters=quarters)
    data = load(warehouse, ciks, names, candidates, data_cutoff, panel)
    data.bankruptcy_filings = bankruptcy_filings(archive, ciks, names)
    counts, examples = count_examples(warehouse, ciks, TARGET, data_cutoff, FIRST_ORIGIN)
    usable = usability(data)
    checks = [check(data) for check in CHECKS]
    checks += [
        leakage_check(archive, warehouse, ciks, leakage_cutoffs, synthetic_macro, now, workers),
        reconciliation_check(warehouse, reconciliation, data_cutoff),
        sample_size_check(counts, len(usable[TARGET])),
        macro_check(real_macro),
    ]
    statuses = Counter(c.status for c in checks)
    blocked = statuses[CheckStatus.FAIL] or statuses[CheckStatus.BLOCKED]
    verdict = (
        GateVerdict.BLOCKED
        if blocked
        else GateVerdict.PASSED_WITH_WARNINGS
        if statuses[CheckStatus.WARNING]
        else GateVerdict.PASSED
    )
    reasons = [
        f"{c.title}: {c.summary}"
        for c in checks
        if c.status in (CheckStatus.FAIL, CheckStatus.BLOCKED)
    ]
    if verdict is GateVerdict.PASSED_WITH_WARNINGS:
        reasons = [f"{statuses[CheckStatus.WARNING]} checks with warnings"]
    digest = examples_hash(examples)
    manifest = GateManifest(
        dataset_id=f"gate-b-{eastern_date(data_cutoff):%Y%m%d}-{digest[:12]}",
        sha256=digest,
        data_cutoff=data_cutoff,
        view=KnowledgeView.VINTAGE,
        target_metric=TARGET,
        first_origin=FIRST_ORIGIN,
        last_origin=quarter_ends(eastern_date(data_cutoff), 1)[0],
        companies=tuple(decisions(data, usable)),
        example_counts=tuple(counts),
        pit_snapshot_id=snapshot.manifest.snapshot_id,
        synthetic_macro=checks[-1].status is not CheckStatus.PASS,
        checks=tuple(checks),
        verdict=verdict,
        verdict_reasons=tuple(reasons),
        contracts_version=CONTRACTS_VERSION,
        created_at=now,
    )
    return GateResult(manifest, data, examples, usable)
