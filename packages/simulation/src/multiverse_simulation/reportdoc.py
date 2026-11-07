"""Report Studio (Stage 25, ADR-0034): a research report from one finished run.

The document is built from the simulation report, its case and its decision only. It reads no
clock and no machine, and it never formats a number it cannot point back to: every number in the
text is a claim with a JSON pointer into the run. Markdown and CSV are rendered from the document,
and a manifest records their hashes. ``replay`` runs the simulation again from the manifest and
compares the files byte for byte.
"""

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from multiverse_contracts.decisions import DecisionModel
from multiverse_contracts.primitives import DataOrigin
from multiverse_contracts.reports import (
    EMPIRICAL_LABEL,
    GENERATOR_VERSION,
    SYNTHETIC_LABEL,
    ClaimUnit,
    EvidenceLevel,
    ReplayCheck,
    ReportArtifact,
    ReportClaim,
    ReportManifest,
    ReportSection,
    ReportTable,
    ResearchReport,
    SectionKey,
    SourceKind,
    SourceRef,
)
from multiverse_contracts.simulation import SimulationCase, SimulationReport
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_finance import __version__ as finance_version
from multiverse_simulation import __version__ as simulation_version

FILES = {"markdown": "report.md", "csv": "report.csv", "document": "document.json"}
DECISION_TITLES = {
    "rnd_change": "R&D budget change",
    "workforce_restructure": "Workforce restructuring",
    "acquisition": "Acquisition",
    "divestiture": "Divestiture or segment exit",
    "capex_expansion": "CAPEX expansion",
    "debt_refinance": "Debt refinancing",
}
METRIC_TITLES = {
    "revenue": "Revenue",
    "ebitda": "EBITDA (calculated)",
    "fcf": "FCFF (unlevered, model)",
    "net_debt": "Net debt",
    "ev": "Enterprise value",
}
SCENARIO_TITLES = {"baseline": "Baseline", "alt_a": "With the decision"}
VALUE_TITLES = {
    "enterprise_value": "Enterprise value (DCF, model)",
    "equity_value": "Equity value (model)",
    "ev_change": "Paired change of enterprise value",
}
SHOWN_QUARTERS = (4, 8)
CAUSAL_NOTE = (
    "No causal effect is estimated here. The feasibility study of Stage 20 found none of its 24 "
    "pairs of method and decision feasible on the data. The difference between the two scenarios "
    "is the assumed mechanics of the decision run through the same shocks, not an effect measured "
    "on companies that made it."
)
LIMITATIONS = (
    "Probabilities and quantiles are conditional on the assumed model: they are not calibrated "
    "and are not confidence intervals.",
    "Enterprise and equity values come from a model DCF: they are model values, not market "
    "values, and no price per share is given.",
    "Where the filings do not give an input, the case implies or assumes it, and the assumptions "
    "section lists each one.",
    "Shocks are blocks of past quarters drawn again: a crisis unlike any of them is not in the "
    "paths.",
)
METHOD_DOCS = (
    ("Financial statement engine, ADR-0029", "docs/adr/0029-financial-engine.md"),
    ("Paired Monte Carlo, ADR-0030", "docs/adr/0030-paired-monte-carlo.md"),
    ("Causal feasibility study, Stage 20", "docs/stages/20-causal-research-pipeline.md"),
    ("Report Studio, ADR-0034", "docs/adr/0034-report-studio.md"),
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_view(
    report: SimulationReport, case: SimulationCase, decision: DecisionModel
) -> dict[str, Any]:
    """What claims point into. Times and seconds stay out: they are not part of a run."""
    return {
        "report": report.model_dump(mode="json"),
        "case": case.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
    }


def resolve(view: Mapping[str, Any], pointer: str) -> Any:
    """A JSON pointer (RFC 6901, without escapes) into the view of a run."""
    node: Any = view
    for part in pointer.strip("/").split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def cik_of(case_id: str) -> str | None:
    """``case-48898-20251231`` -> ``48898``: cases of real filers carry the CIK."""
    middle = case_id.removeprefix("case-").rsplit("-", 1)[0]
    return middle if middle.isdigit() else None


def filing_url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"


@dataclass
class Scale:
    """Billions for large companies, millions for the rest; one scale per report."""

    divisor: Decimal
    word: str

    def money(self, value: str | None) -> str:
        if value is None:
            return "undefined"
        amount = Decimal(value) / self.divisor
        sign = "−" if amount < 0 else ""
        return f"{sign}{abs(amount):,.1f}"

    @property
    def unit(self) -> str:
        return f"USD {self.word}"


def scale_of(report: SimulationReport) -> Scale:
    revenue = next(m for m in report.result.metrics if m.metric.value == "revenue")
    largest = max(abs(Decimal(p.p50)) for s in revenue.forecasts for p in s.points)
    return Scale(Decimal(10**9), "bn") if largest >= 10**9 else Scale(Decimal(10**6), "m")


@dataclass
class Builder:
    view: dict[str, Any]
    claims: list[ReportClaim] = field(default_factory=list)
    refs: list[SourceRef] = field(default_factory=list)

    def ref(self, kind: SourceKind, label: str, target: str, record: str | None = None) -> str:
        for known in self.refs:
            if known.target == target:
                return known.ref_id
        ref_id = f"S{len(self.refs) + 1}"
        self.refs.append(
            SourceRef(ref_id=ref_id, kind=kind, label=label, target=target, record=record)
        )
        return ref_id

    def claim(
        self,
        statement: str,
        pointer: str,
        unit: ClaimUnit,
        sources: Sequence[str],
        shown: Callable[[str], str] = str,
    ) -> str:
        """Text for the claim, ``value [C3]``, after checking the pointer finds that value."""
        value = resolve(self.view, pointer)
        if value is None or isinstance(value, (dict, list)):
            raise ValueError(f"{pointer} is not a single value")
        claim_id = f"C{len(self.claims) + 1}"
        self.claims.append(
            ReportClaim(
                claim_id=claim_id,
                statement=statement,
                value=str(value),
                unit=unit,
                pointer=pointer,
                sources=tuple(sources),
            )
        )
        return f"{shown(str(value))} [{claim_id}]"


def _index(items: Iterable[Mapping[str, Any]], **match: str) -> int:
    for number, item in enumerate(items):
        if all(item.get(key) == value for key, value in match.items()):
            return number
    raise KeyError(f"no item with {match}")


def _percent(value: str) -> str:
    return f"{100 * float(value):.1f}%"


def _decision_rows(payload: Mapping[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key, value in payload.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            rows += _decision_rows(value, f"{name}.")
        elif value is not None:
            rows.append((name, str(value)))
    return rows


def _sources(builder: Builder, case: SimulationCase) -> dict[str, str]:
    """The references every report has; filings are added by the coverage section."""
    found: dict[str, str] = {}
    if case.data_origin is DataOrigin.SYNTHETIC:
        found["data"] = builder.ref(
            SourceKind.METHOD,
            "Synthetic fixture of the simulation package: invented company and figures",
            "packages/simulation/src/multiverse_simulation/example.py",
        )
    else:
        found["data"] = builder.ref(
            SourceKind.DATA_SOURCE,
            "SEC EDGAR filings (XBRL company facts)",
            "/data-catalog/sec-edgar",
        )
        if "World Bank" in case.shocks.method:
            found["rates"] = builder.ref(
                SourceKind.DATA_SOURCE, "U.S. Treasury par yield curve", "/data-catalog/us-treasury"
            )
            found["gdp"] = builder.ref(
                SourceKind.DATA_SOURCE,
                "World Bank GDP growth, CC BY 4.0",
                "/data-catalog/world-bank",
            )
            found["ecb"] = builder.ref(
                SourceKind.DATA_SOURCE,
                "Source: ECB statistics (features of the model)",
                "/data-catalog/ecb-data-portal",
            )
        else:
            found["rates"] = builder.ref(
                SourceKind.DATA_SOURCE,
                "FRED series of a Stage 22 case (licence block LIC-001)",
                "/data-catalog/fred-alfred",
            )
    if case.dataset_id:
        found["dataset"] = builder.ref(SourceKind.DATASET, "Forecasting dataset", case.dataset_id)
    if case.model_id:
        found["model"] = builder.ref(
            SourceKind.MODEL, "Model of the central margin path", case.model_id
        )
    found["run"] = builder.ref(
        SourceKind.RUN, "Paired Monte Carlo run", builder.view["report"]["manifest"]["report_id"]
    )
    for label, path in METHOD_DOCS:
        found[path] = builder.ref(SourceKind.METHOD, label, path)
    return found


def build_document(
    report: SimulationReport, case: SimulationCase, decision: DecisionModel
) -> ResearchReport:
    view = run_view(report, case, decision)
    builder = Builder(view)
    refs = _sources(builder, case)
    scale = scale_of(report)
    run, data = refs["run"], refs["data"]
    synthetic = case.data_origin is DataOrigin.SYNTHETIC
    kind = DECISION_TITLES[decision.type]
    horizon = case.horizon
    sections = [
        _objective(builder, report, case, kind, horizon, run),
        _cutoff(builder, report, case, data),
        _coverage(builder, report, case, refs),
        _action(builder, decision, kind, run),
        _models(builder, report, case, refs),
        _results(builder, report, scale, run),
        ReportSection(
            key=SectionKey.CAUSAL,
            title="Causal status",
            paragraphs=(CAUSAL_NOTE, "Evidence level: conditional simulation."),
        ),
        _assumptions(report),
        _sensitivity(builder, report, scale, run),
        _limitations(report),
    ]
    identity = sha256(f"{report.manifest.report_id}|{GENERATOR_VERSION}".encode())[:12]
    title = f"{case.company_name}: {kind}, {horizon} quarters from {case.as_of}"
    return ResearchReport(
        contracts_version=CONTRACTS_VERSION,
        generator_version=GENERATOR_VERSION,
        report_doc_id=f"rep-{case.as_of:%Y%m%d}-{identity}",
        simulation_report_id=report.manifest.report_id,
        title=f"Synthetic demonstration. {title}" if synthetic else title,
        company_id=case.company_id,
        company_name=case.company_name,
        as_of=case.as_of,
        data_origin=case.data_origin,
        evidence_level=EvidenceLevel.SYNTHETIC_DEMO
        if synthetic
        else EvidenceLevel.CONDITIONAL_SIMULATION,
        label=SYNTHETIC_LABEL if synthetic else EMPIRICAL_LABEL,
        sections=tuple(sections),
        claims=tuple(builder.claims),
        sources=tuple(builder.refs),
    )


def _objective(
    builder: Builder,
    report: SimulationReport,
    case: SimulationCase,
    kind: str,
    horizon: int,
    run: str,
) -> ReportSection:
    paths = builder.claim("Paths simulated", "/report/diagnostics/paths", "paths", [run])
    seed = builder.claim("Seed of the run", "/report/manifest/settings/seed", "count", [run])
    return ReportSection(
        key=SectionKey.OBJECTIVE,
        title="Scenario objective",
        paragraphs=(
            f"What would the decision below, {kind}, change for {case.company_name} over the "
            f"next {horizon} quarters, compared with the same company without it, under the "
            "same shocks?",
            f"{paths} paired paths, seed {seed}. Each path runs the company twice, with and "
            "without the decision, on the same draw of shocks, so the difference is not noise "
            "between two draws.",
        ),
    )


def _cutoff(
    builder: Builder, report: SimulationReport, case: SimulationCase, data: str
) -> ReportSection:
    as_of = builder.claim("Knowledge cutoff", "/case/as_of", "date", [data])
    balance = builder.claim("Opening balance date", "/case/balance_date", "date", [data])
    return ReportSection(
        key=SectionKey.CUTOFF,
        title="Historical cutoff",
        paragraphs=(
            f"Only what was public by {as_of} is used. The opening balance is the last quarter "
            f"reported by then, {balance}; the paths start after it.",
        ),
    )


def _coverage(
    builder: Builder, report: SimulationReport, case: SimulationCase, refs: Mapping[str, str]
) -> ReportSection:
    data = refs["data"]
    quarters = builder.claim(
        "Quarters of shock history", "/report/diagnostics/history_quarters", "quarters", [data]
    )
    peers = builder.claim("Firms behind the sector columns", "/case/shocks/peers", "count", [data])
    cik = cik_of(case.case_id)
    rows = []
    for point in case.history:
        accession = point.source_id.removeprefix("sec:")
        if cik is not None and point.source_id.startswith("sec:"):
            ref = builder.ref(
                SourceKind.SEC_FILING,
                f"SEC filing {accession}, {point.fiscal_label}",
                filing_url(cik, accession),
            )
        else:
            ref = data
        rows.append(
            (
                point.fiscal_label,
                str(point.period_end),
                str(point.filed_at),
                "yes" if point.revenue is not None else "no",
                "yes" if point.ebitda is not None else "no",
                "yes" if point.fcf is not None else "no",
                ref,
            )
        )
    table = ReportTable(
        caption="Quarters of the case and the filing each one comes from",
        columns=("Quarter", "Period end", "Filed", "Revenue", "EBITDA", "FCF", "Source"),
        rows=tuple(rows),
    )
    sources = ", ".join(sorted({row[-1] for row in rows}, key=lambda r: int(r[1:])))
    return ReportSection(
        key=SectionKey.SOURCES,
        title="Source coverage",
        paragraphs=(
            f"The case reads {len(rows)} reported quarters ({sources or data}). Shocks come from "
            f"{quarters} past quarters of {peers} firms of the same division.",
        ),
        tables=(table,),
    )


def _action(builder: Builder, decision: DecisionModel, kind: str, run: str) -> ReportSection:
    payload = builder.view["decision"]
    rows = tuple((name, value) for name, value in _decision_rows(payload) if name != "type")
    return ReportSection(
        key=SectionKey.ACTION,
        title="Action definition",
        paragraphs=(
            f"Decision type: {kind}. The fields below are the decision exactly as the run used "
            f"it ({run}); ranges are drawn on every path.",
        ),
        tables=(ReportTable(caption="The decision", columns=("Field", "Value"), rows=rows),),
    )


def _models(
    builder: Builder, report: SimulationReport, case: SimulationCase, refs: Mapping[str, str]
) -> ReportSection:
    engine = refs["docs/adr/0029-financial-engine.md"]
    simulation = refs["docs/adr/0030-paired-monte-carlo.md"]
    model = refs.get("model")
    paragraphs = [
        f"Central path. Growth: {case.central.growth_source} Margin: "
        f"{case.central.margin_source}" + (f" ({model})" if model else ""),
        f"Finance: the statement engine {finance_version} ({engine}) turns each path into "
        f"reconciled statements and a model DCF. Simulation {simulation_version} ({simulation}).",
        f"Shocks: {case.shocks.method}",
    ]
    if "dataset" in refs:
        paragraphs.append(f"Dataset {case.dataset_id} ({refs['dataset']}).")
    return ReportSection(
        key=SectionKey.MODELS, title="Forecast and finance model", paragraphs=tuple(paragraphs)
    )


def _results(builder: Builder, report: SimulationReport, scale: Scale, run: str) -> ReportSection:
    view = builder.view["report"]
    metrics = view["result"]["metrics"]
    rows = []
    for metric in metrics:
        for series in metric["forecasts"]:
            for quarter in (*SHOWN_QUARTERS, len(series["points"])):
                if quarter > len(series["points"]):
                    continue
                point = series["points"][quarter - 1]
                rows.append(
                    (
                        METRIC_TITLES[metric["metric"]],
                        SCENARIO_TITLES.get(series["scenario"], series["scenario"]),
                        point["fiscal_label"],
                        scale.money(point["p10"]),
                        scale.money(point["p50"]),
                        scale.money(point["p90"]),
                    )
                )
    quantiles = ReportTable(
        caption="Quantiles across paths, by quarter after the cutoff",
        columns=("Metric", "Scenario", "Quarter", "p10", "p50", "p90"),
        rows=tuple(dict.fromkeys(rows)),
        unit_note=scale.unit,
    )
    values = ReportTable(
        caption="Model values at the cutoff",
        columns=("Value", "Scenario", "p10", "p50", "p90", "Undefined on"),
        rows=tuple(
            (
                VALUE_TITLES[row["metric"]],
                SCENARIO_TITLES[row["scenario"]],
                scale.money(row["p10"]),
                scale.money(row["p50"]),
                scale.money(row["p90"]),
                _percent(str(row["undefined_share"])),
            )
            for row in view["values"]
        ),
        unit_note=scale.unit,
    )
    risks = ReportTable(
        caption="Share of paths with each event within the horizon",
        columns=("Event", "Scenario", "Share", "Monte Carlo error", "Upper 95%"),
        rows=tuple(
            (
                row["label"],
                SCENARIO_TITLES[row["scenario"]],
                _percent(str(row["probability"])),
                _percent(str(row["standard_error"])),
                _percent(str(row["upper_95"])),
            )
            for row in view["risks"]
        ),
    )
    ev = _index(view["values"], metric="enterprise_value", scenario="baseline")
    alt = _index(view["values"], metric="enterprise_value", scenario="alt_a")
    change = _index(view["values"], metric="ev_change", scenario="alt_a")
    money = scale.money
    base_p50 = builder.claim(
        "Median model EV without the decision", f"/report/values/{ev}/p50", "usd", [run], money
    )
    alt_p50 = builder.claim(
        "Median model EV with the decision", f"/report/values/{alt}/p50", "usd", [run], money
    )
    low = builder.claim(
        "p10 of the paired EV change", f"/report/values/{change}/p10", "usd", [run], money
    )
    middle = builder.claim(
        "Median paired EV change", f"/report/values/{change}/p50", "usd", [run], money
    )
    high = builder.claim(
        "p90 of the paired EV change", f"/report/values/{change}/p90", "usd", [run], money
    )
    covenant = _index(view["risks"], risk="covenant_breach", scenario="alt_a")
    breach = builder.claim(
        "Share of paths with a covenant breach, with the decision",
        f"/report/risks/{covenant}/probability",
        "share",
        [run],
        _percent,
    )
    return ReportSection(
        key=SectionKey.RESULTS,
        title="Results",
        paragraphs=(
            f"The median model enterprise value is {scale.unit} {base_p50} without the decision "
            f"and {scale.unit} {alt_p50} with it. Path by path, the change has a median of "
            f"{scale.unit} {middle}, from {low} at p10 to {high} at p90.",
            f"A covenant breach happens on {breach} of the paths with the decision. "
            f"{report.probability_label}.",
        ),
        tables=(quantiles, values, risks),
    )


def _assumptions(report: SimulationReport) -> ReportSection:
    counts = {origin: 0 for origin in ("observed", "implied", "assumed", "model")}
    for item in report.inputs:
        counts[item.origin] += 1
    return ReportSection(
        key=SectionKey.ASSUMPTIONS,
        title="Assumptions",
        paragraphs=(
            f"{len(report.inputs)} inputs: {counts['observed']} observed in filings, "
            f"{counts['implied']} implied from them, {counts['model']} from a model and "
            f"{counts['assumed']} assumed.",
        ),
        tables=(
            ReportTable(
                caption="How each input is known",
                columns=("Input", "Known as", "Note"),
                rows=tuple((item.name, item.origin, item.note) for item in report.inputs),
            ),
        ),
    )


def _sensitivity(
    builder: Builder, report: SimulationReport, scale: Scale, run: str
) -> ReportSection:
    if not report.sensitivity:
        return ReportSection(
            key=SectionKey.SENSITIVITY,
            title="Sensitivity",
            paragraphs=("This run has no sensitivity variants.",),
        )
    rows = tuple(
        (
            row.label,
            str(row.paths),
            scale.money(row.ebitda_p10),
            scale.money(row.ebitda_p50),
            scale.money(row.ebitda_p90),
            scale.money(row.ev_change_p50),
            _percent(str(row.covenant_probability)),
        )
        for row in report.sensitivity
    )
    return ReportSection(
        key=SectionKey.SENSITIVITY,
        title="Sensitivity",
        paragraphs=(
            "The same decision with one choice of the shock model changed, on fewer paths "
            f"({run}). EBITDA is at the last quarter, with the decision.",
        ),
        tables=(
            ReportTable(
                caption="Sensitivity to the shock model",
                columns=(
                    "Variant",
                    "Paths",
                    "EBITDA p10",
                    "EBITDA p50",
                    "EBITDA p90",
                    "EV change p50",
                    "Covenant breach",
                ),
                rows=rows,
                unit_note=scale.unit,
            ),
        ),
    )


def _limitations(report: SimulationReport) -> ReportSection:
    flags = tuple(report.diagnostics.flags)
    clipped = _percent(str(report.diagnostics.clipped_share))
    undefined = _percent(str(report.diagnostics.ev_undefined_share))
    return ReportSection(
        key=SectionKey.LIMITATIONS,
        title="Limitations",
        paragraphs=(
            *LIMITATIONS,
            f"Shocks met a hard bound in {clipped} of quarters. Enterprise value is undefined on "
            f"{undefined} of paths: the values table counts them.",
            *flags,
        ),
    )


# Rendering ----------------------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(doc: ResearchReport) -> str:
    refs = {ref.ref_id: ref for ref in doc.sources}
    lines = [
        f"# {doc.title}",
        "",
        f"> **{doc.label}.**",
        "",
        f"Report `{doc.report_doc_id}` from run `{doc.simulation_report_id}`, "
        f"generator `{doc.generator_version}`, contracts `{doc.contracts_version}`. "
        f"Company `{doc.company_id}`, cutoff {doc.as_of}, evidence level "
        f"`{doc.evidence_level.value}`.",
    ]
    for number, section in enumerate(doc.sections, start=1):
        lines += ["", f"## {number}. {section.title}", ""]
        for paragraph in section.paragraphs:
            lines += [paragraph, ""]
        for table in section.tables:
            caption = f"*{table.caption}" + (f", {table.unit_note}*" if table.unit_note else "*")
            lines += [caption, "", "| " + " | ".join(table.columns) + " |"]
            lines.append("|" + "|".join("---" for _ in table.columns) + "|")
            lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in table.rows]
            lines.append("")
    lines += ["", "## Claims", "", "| Claim | Statement | Value | Unit | Pointer | Sources |"]
    lines.append("|---|---|---|---|---|---|")
    for claim in doc.claims:
        lines.append(
            f"| {claim.claim_id} | {_cell(claim.statement)} | {claim.value} | {claim.unit} | "
            f"`{claim.pointer}` | {', '.join(claim.sources)} |"
        )
    lines += ["", "## Sources", ""]
    for ref in refs.values():
        target = ref.target
        shown = f"<{target}>" if target.startswith("https://") else f"`{target}`"
        lines.append(f"- **{ref.ref_id}** {ref.label} ({ref.kind.value}): {shown}")
    return "\n".join(lines).rstrip() + "\n"


def render_csv(doc: ResearchReport, report: SimulationReport) -> str:
    """Tidy rows in full units: one statistic per line, for a spreadsheet to check."""
    out = ["table,metric,scenario,period,statistic,value,unit"]

    def add(*cells: object) -> None:
        out.append(",".join(_csv(str(c)) for c in cells))

    for metric in report.result.metrics:
        for series in metric.forecasts:
            for point in series.points:
                for statistic in ("p10", "p50", "p90"):
                    add(
                        "quantiles",
                        metric.metric.value,
                        series.scenario,
                        point.period_end,
                        statistic,
                        getattr(point, statistic),
                        report.result.currency,
                    )
    for row in report.values:
        for statistic in ("p1", "p10", "p50", "p90", "p99", "mean"):
            value = getattr(row, statistic)
            if value is not None:
                add("values", row.metric, row.scenario, doc.as_of, statistic, value, "USD")
    for risk in report.risks:
        add("risks", risk.risk, risk.scenario, "horizon", "probability", risk.probability, "share")
        add(
            "risks",
            risk.risk,
            risk.scenario,
            "horizon",
            "standard_error",
            risk.standard_error,
            "share",
        )
    return "\n".join(out) + "\n"


def _csv(text: str) -> str:
    if any(ch in text for ch in ',"\n') or (text[:1] in "=+-@\t\r" and not _number(text)):
        return '"' + text.replace('"', '""') + '"'
    return text


def _number(text: str) -> bool:
    try:
        Decimal(text)
    except ArithmeticError:
        return False
    return True


# Files and replay ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Written:
    document: ResearchReport
    manifest: ReportManifest
    files: dict[str, bytes]


def render_files(
    report: SimulationReport, case: SimulationCase, decision: DecisionModel
) -> Written:
    document = build_document(report, case, decision)
    files = {
        FILES["markdown"]: render_markdown(document).encode(),
        FILES["csv"]: render_csv(document, report).encode(),
        FILES["document"]: document.model_dump_json(indent=2).encode() + b"\n",
    }
    artifacts = tuple(
        ReportArtifact(format=kind, file=name, sha256=sha256(files[name]), bytes=len(files[name]))  # type: ignore[arg-type]
        for kind, name in FILES.items()
    )
    manifest = ReportManifest(
        report_doc_id=document.report_doc_id,
        generator_version=GENERATOR_VERSION,
        contracts_version=CONTRACTS_VERSION,
        simulation_report_id=report.manifest.report_id,
        case_id=case.case_id,
        case_sha256=report.manifest.case_sha256,
        decision=decision,
        decision_sha256=report.manifest.decision_sha256,
        settings=report.manifest.settings,
        sensitivity=bool(report.sensitivity),
        dataset_id=case.dataset_id,
        dataset_sha256=case.dataset_sha256,
        model_id=case.model_id,
        finance_version=finance_version,
        simulation_version=simulation_version,
        artifacts=artifacts,
    )
    return Written(document, manifest, files)


def write_report_files(
    folder: Path, report: SimulationReport, case: SimulationCase, decision: DecisionModel
) -> ReportManifest:
    """Idempotent: a second call writes the same bytes, and leaves an equal file untouched."""
    written = render_files(report, case, decision)
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        **written.files,
        "manifest.json": written.manifest.model_dump_json(indent=2).encode() + b"\n",
    }
    for name, data in files.items():
        path = folder / name
        if path.exists() and path.read_bytes() == data:
            continue
        pending = folder / f"{name}.pending"
        pending.write_bytes(data)
        pending.replace(path)
    return written.manifest


def replay(
    manifest: ReportManifest,
    folder: Path,
    case: SimulationCase,
    run: Callable[[SimulationCase, DecisionModel, Any, bool], SimulationReport],
) -> ReplayCheck:
    """Run the simulation again from the manifest and compare every file with the one in folder."""
    if sha256(case.model_dump_json().encode()) != manifest.case_sha256:
        raise ValueError(f"{case.case_id} is not the case of {manifest.report_doc_id}")
    report = run(case, manifest.decision, manifest.settings, manifest.sensitivity)
    written = render_files(report, case, manifest.decision)
    checks = []
    for artifact in manifest.artifacts:
        stored = (folder / artifact.file).read_bytes()
        again = written.files[artifact.file]
        checks.append(
            (
                artifact.format,
                sha256(stored) == artifact.sha256 == sha256(again) and stored == again,
            )
        )
    return ReplayCheck(
        report_doc_id=manifest.report_doc_id,
        artifacts=tuple(checks),
        identical=all(ok for _, ok in checks)
        and written.document.report_doc_id == manifest.report_doc_id,
    )
