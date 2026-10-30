"""The data card and the visual coverage report of Gate B (DATA-05).

Written to ``var/data/gate/`` (never committed):

    manifest.json   GateManifest: companies, example counts, checks, verdict, hash
    examples.csv    every trainable example (company, origin, history, horizon, target)
    data-card.md    what the dataset is, what it holds, what it must not be used for
    coverage.html   charts and tables by company, sector, metric, year, currency, standard
"""

import csv
import html
import io
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

from multiverse_contracts.pit import MASKED_STATES, CellState
from multiverse_contracts.quality import CheckStatus, GateManifest
from multiverse_contracts.sources import CompanyCandidate, SectorPriority
from multiverse_pipelines.audit.checks import AuditData
from multiverse_pipelines.audit.examples import HISTORIES, HORIZONS, Example
from multiverse_pipelines.pit.clock import eastern_date
from multiverse_pipelines.pit.panel import PANEL_METRICS
from multiverse_pipelines.sec.universe import division

# Above this many companies the report groups them (by SIC division) instead of listing.
LISTED_COMPANIES = 40
STATUS_LABEL = {
    CheckStatus.PASS: "pass",
    CheckStatus.WARNING: "warning",
    CheckStatus.FAIL: "fail",
    CheckStatus.BLOCKED: "blocked",
}


def sector_of(candidate: CompanyCandidate, sectors: Sequence[SectorPriority]) -> str:
    code = int(candidate.sic)
    for sector in sectors:
        for item in sector.sic_codes:
            low, _, high = item.partition("-")
            if int(low) <= code <= int(high or low):
                return sector.sector
    return candidate.sic_description


def group_of(data: AuditData, cik: str, sectors: Sequence[SectorPriority]) -> str:
    """The sector of a catalog candidate, or the SIC division of a universe company."""
    if data.universe is not None:
        company = next((c for c in data.universe.companies if c.cik == cik), None)
        if company is not None:
            letter, title = division(company.sic)
            return f"{letter} {title}"
    candidate = data.candidates.get(cik)
    return sector_of(candidate, sectors) if candidate else "unknown"


def _names(names: Sequence[str], limit: int = 10) -> str:
    shown = ", ".join(names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


def _scope(data: AuditData) -> str:
    if data.universe is None:
        return "the SEC sample of decision D-09"
    return f"the universe `{data.universe.universe_id}` of decision D-10"


def coverage_by(data: AuditData, key: str) -> dict[str, tuple[int, int]]:
    """Masked cells and cells where a report was public, grouped by a key."""
    found: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for cell in data.panel.cells:
        if cell.state in (CellState.INACTIVE, CellState.NOT_COVERED, CellState.NOT_YET_FILED):
            continue
        group = {
            "company": data.name(cell.cik),
            "metric": cell.metric,
            "year": cell.calendar_quarter[:4],
        }[key]
        found[group][1] += 1
        found[group][0] += cell.state in MASKED_STATES
    return {k: (v[0], v[1]) for k, v in found.items()}


def _share(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{100 * part / whole:.1f}%"


def examples_csv(examples: Sequence[Example]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        (
            "cik",
            "origin",
            "history_quarters",
            "horizon_quarters",
            "target_quarter",
            "target_revenue",
        )
    )
    for e in sorted(examples, key=lambda e: (e.cik, e.origin, e.history, e.horizon)):
        writer.writerow(
            (
                e.cik,
                e.origin.isoformat(),
                e.history,
                e.horizon,
                e.target_quarter.isoformat(),
                e.target,
            )
        )
    return buffer.getvalue()


def data_card(
    manifest: GateManifest,
    data: AuditData,
    sectors: Sequence[SectorPriority],
    usable: dict[str, list[str]],
    standards: Counter[str],
) -> str:
    lines = [
        f"# Data card: MULTIVERSE financial dataset `{manifest.dataset_id}`",
        "",
        f"Gate B verdict: **{manifest.verdict.value}**. "
        f"Data cutoff {eastern_date(manifest.data_cutoff)} (end of day, US Eastern); "
        f"point-in-time view `{manifest.view.value}`; PIT snapshot `{manifest.pit_snapshot_id}`; "
        f"SHA-256 of the examples `{manifest.sha256}`.",
        "",
        "## What it is",
        "",
        "Quarterly financial values of US companies from SEC XBRL filings (Company Facts), "
        "normalized into 16 metrics with lineage (Stage 11) and placed by the moment each "
        "filing became public (Stage 12). Every value can be traced to its filing on sec.gov.",
        "",
        "## Composition",
        "",
    ]
    decided = {d.cik: d for d in manifest.companies}
    if data.universe is not None:
        universe = data.universe
        lines += [
            f"{len(data.ciks)} companies drawn with seed {universe.seed} from "
            f"{universe.rules[-1].remaining} eligible US filers; the list is in "
            f"`data/universe/{universe.universe_id}.json`.",
            "",
            "| SIC division | Eligible | Chosen | Deregistered | In the revenue dataset |",
            "|---|---|---|---|---|",
        ]
        for stratum in universe.strata:
            mine = [c for c in universe.companies if c.division == stratum.division]
            lines.append(
                f"| {stratum.division} {stratum.title} | {stratum.eligible} | {stratum.selected} "
                f"| {sum(c.deregistered for c in mine)} "
                f"| {sum(decided[c.cik].include for c in mine if c.cik in decided)} |"
            )
    else:
        lines += [
            "| Company | CIK | Sector | SIC | Fiscal year end | Filer | Status | Revenue dataset |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for cik in data.ciks:
            c = data.candidates.get(cik)
            if c is None:
                continue
            d = decided[cik]
            lines.append(
                f"| {c.name} | {cik} | {sector_of(c, sectors)} | {c.sic} | {c.fiscal_year_end} "
                f"| {c.filer_category} | {c.status} | {'included' if d.include else 'excluded'} |"
            )
    currencies = Counter(r.currency for rows in data.current.values() for r in rows if r.currency)
    lines += [
        "",
        "Currency: "
        + ", ".join(f"{k} ({v} values)" for k, v in currencies.items())
        + "; no FX conversion. Reporting standard: "
        + ", ".join(f"{k} ({v} values)" for k, v in standards.most_common())
        + ".",
        "",
        "## Usable size",
        "",
        "Counted in usable examples, not in downloaded files. An example is a company and a "
        "forecast origin with the last H quarters of revenue all public at the origin and the "
        "revenue h quarters later as first released.",
        "",
        "| History H \\ horizon h | " + " | ".join(str(h) for h in HORIZONS) + " |",
        "|---|" + "---|" * len(HORIZONS),
    ]
    for history in HISTORIES:
        cells = [
            next(
                f"{c.examples} ({c.companies} cos)"
                for c in manifest.example_counts
                if c.history_quarters == history and c.horizon_quarters == h
            )
            for h in HORIZONS
        ]
        lines.append(f"| {history} | " + " | ".join(cells) + " |")
    lines += ["", "Companies with at least 12 quarters, per metric:", ""]
    for metric in PANEL_METRICS:
        names = [data.name(c) for c in usable[metric]]
        missing = [data.name(c) for c in data.ciks if c not in usable[metric]]
        lines.append(
            f"- `{metric}`: {len(names)} of {len(data.ciks)}"
            + (f" (missing: {_names(missing)})" if missing else "")
        )
    lines += [
        "",
        "## Coverage by metric",
        "",
        "| Metric | With value where a report was public |",
        "|---|---|",
    ]
    for metric, (masked, total) in sorted(coverage_by(data, "metric").items()):
        lines.append(f"| {metric} | {masked} of {total} ({_share(masked, total)}) |")
    lines += ["", "## Quality checks", "", "| Check | Status | Summary |", "|---|---|---|"]
    for check in manifest.checks:
        lines.append(f"| {check.title} | {STATUS_LABEL[check.status]} | {check.summary} |")
    lines += ["", "## Known biases and limits", "", *_limits(manifest, data), ""]
    lines += [
        "## Intended use",
        "",
        "Pipeline validation and pilot baselines that state the sample. Not for claims about "
        "companies in general, sectors, or decision effects."
        if data.universe is None
        else "Training and evaluation of forecasting baselines for US non-financial filers "
        "with three or more years of XBRL reports, within the limits above. Not for claims "
        "about decision effects: nothing here identifies a cause.",
        "",
        "## Sources and licence",
        "",
        "SEC EDGAR filings (public domain in the US; fair access rules, User-Agent declared). "
        "Raw files and derived tables stay in `var/` and are never committed.",
        "",
    ]
    if manifest.verdict_reasons:
        lines += ["## Why the verdict", ""] + [f"- {r}" for r in manifest.verdict_reasons] + [""]
    return "\n".join(lines)


def _limits(manifest: GateManifest, data: AuditData) -> list[str]:
    bankruptcies = len(data.bankruptcy_filings)
    failing = (
        "No bankruptcies."
        if not bankruptcies
        else f"{bankruptcies} bankruptcy filings (8-K item 1.03): failing companies are rare."
    )
    if data.universe is None:
        lines = [
            "- Ten companies chosen in 2026 by a rubric (decision D-09), nine still listed: a "
            f"survivor-heavy, large-cap, US-only sample. {failing}",
            "- One company per sector at most: sector effects cannot be learned.",
        ]
    else:
        gone = sum(c.deregistered for c in data.universe.companies)
        lines = [
            f"- Drawn from every eligible filer, active or not ({gone} of "
            f"{len(data.universe.companies)} have deregistered), but each needed 12 XBRL "
            "reports: companies that failed within three years of their first XBRL report, "
            "foreign private issuers (20-F) and the excluded financial sectors are absent. "
            + failing,
            "- XBRL begins in 2009 (large filers) and 2011 (all filers): no earlier history.",
        ]
    if manifest.synthetic_macro:
        lines.append("- No real macro values: only the synthetic store exists (D-11, D-12).")
    else:
        lines.append(
            "- Macro: FRED/ALFRED vintages and ECB series by publication rules; World Bank "
            "indicators are one current snapshot, unusable at historical cutoffs."
        )
    lines.append("- Share counts are not adjusted for stock splits.")
    return lines


CSS = """
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1f21;--muted:#5d6166;--line:#dcdcd6;--bar:#2f5d8a;
--good:#2f7a4f;--warn:#9a6a00;--bad:#a33b3b;--empty:#eceae4}
@media (prefers-color-scheme: dark){:root{--bg:#141516;--panel:#1d1f21;--ink:#e8e8e3;
--muted:#a3a6aa;--line:#34373a;--bar:#8db6df;--good:#7ec79b;--warn:#e0b45c;--bad:#e48a8a;
--empty:#26282b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 8px}
.lede{color:var(--muted);margin:0 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:13px}
.box{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600}.wrap{white-space:normal;text-align:left}
.pass{color:var(--good)}.warning{color:var(--warn)}.fail,.blocked{color:var(--bad)}
.heat td{text-align:center;min-width:38px}.heat td:first-child{text-align:left}
td .wrap{display:block}.bars td.barcell{width:60%}
.bar{display:inline-block;height:10px;border-radius:2px;background:var(--bar)}
"""


def _esc(text: object) -> str:
    return html.escape(str(text))


def _table(head: Sequence[str], rows: Sequence[Sequence[str]], cls: str = "") -> str:
    th = "".join(f"<th>{_esc(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return (
        f"<div class='box {cls}'><table><thead><tr>{th}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def _bars(rows: Sequence[tuple[str, float, str]]) -> str:
    """Horizontal bars in a table: they keep the text size at every width."""
    body = "".join(
        f"<tr><td>{_esc(label)}</td><td class=barcell><span class=bar "
        f"style='width:{max(1, round(100 * share))}%'></span></td><td>{_esc(text)}</td></tr>"
        for label, share, text in rows
    )
    return f"<div class=box><table class=bars><tbody>{body}</tbody></table></div>"


def coverage_html(
    manifest: GateManifest,
    data: AuditData,
    sectors: Sequence[SectorPriority],
    standards: Counter[str],
) -> str:
    by_metric = coverage_by(data, "metric")
    by_year = coverage_by(data, "year")
    years = sorted(by_year)
    grouped = len(data.ciks) > LISTED_COMPANIES
    groups = {cik: group_of(data, cik, sectors) for cik in data.ciks}
    heat: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for cell in data.panel.cells:
        if cell.state in (CellState.INACTIVE, CellState.NOT_COVERED, CellState.NOT_YET_FILED):
            continue
        slot = heat[(groups[cell.cik] if grouped else cell.cik, cell.calendar_quarter[:4])]
        slot[1] += 1
        slot[0] += cell.state in MASKED_STATES
    heat_rows = []
    for cik in sorted(set(groups.values())) if grouped else data.ciks:
        row = [_esc(cik if grouped else data.name(cik))]
        for year in years:
            masked, total = heat.get((cik, year), [0, 0])
            share = masked / total if total else 0
            style = (
                f"background:rgba(47,122,79,{0.1 + 0.85 * share:.2f})"
                if total
                else "background:var(--empty)"
            )
            row.append(
                f"<span title='{masked} of {total}'>{round(100 * share) if total else '-'}</span>"
            )
            row[-1] = f"<div style='{style};padding:2px'>{row[-1]}</div>"
        heat_rows.append(row)
    metric_bars = [
        (m, masked / total if total else 0, f"{_share(masked, total)} of {total}")
        for m, (masked, total) in sorted(
            by_metric.items(), key=lambda kv: -kv[1][0] / max(kv[1][1], 1)
        )
    ]
    example_rows = [
        [f"H = {history}"]
        + [
            str(
                next(
                    c.examples
                    for c in manifest.example_counts
                    if c.history_quarters == history and c.horizon_quarters == h
                )
            )
            for h in HORIZONS
        ]
        for history in HISTORIES
    ]
    sector_rows = []
    by_sector: dict[str, list[str]] = defaultdict(list)
    for cik in data.ciks:
        if data.universe is not None or cik in data.candidates:
            by_sector[groups[cik]].append(data.name(cik))
    for sector, names in sorted(by_sector.items()):
        sector_rows.append(
            [_esc(sector), str(len(names)), f"<span class='wrap'>{_esc(_names(names))}</span>"]
        )
    check_rows = [
        [
            _esc(c.title),
            f"<span class='{c.status.value}'>{STATUS_LABEL[c.status]}</span>",
            f"<span class='wrap'>{_esc(c.summary)}</span>",
        ]
        for c in manifest.checks
    ]
    currencies = Counter(r.currency for rows in data.current.values() for r in rows if r.currency)
    main = next(
        c for c in manifest.example_counts if c.history_quarters == 12 and c.horizon_quarters == 4
    )
    usable_companies = sum(d.include for d in manifest.companies)
    revenue = by_metric.get("revenue", (0, 0))
    kpis = [
        (str(len(data.ciks)), "companies"),
        (str(usable_companies), "with 12+ revenue quarters"),
        (str(main.examples), "examples, H = 12, h = 4"),
        (_share(*revenue), "revenue present where public"),
        (manifest.verdict.value.replace("_", " "), "Gate B verdict"),
    ]
    tiles = "".join(
        f"<div class='kpi'><b>{_esc(v)}</b><span>{_esc(t)}</span></div>" for v, t in kpis
    )
    sections = [
        "<h1>Gate B: financial dataset coverage</h1>",
        f"<p class='lede'>Dataset <code>{_esc(manifest.dataset_id)}</code> · data cutoff "
        f"{eastern_date(manifest.data_cutoff)} (end of day, US Eastern) · point-in-time view · "
        f"measured on the local archive of {_esc(_scope(data)).replace('`', '')}. Size is "
        "counted in usable examples, not files.</p>",
        f"<section class='kpis'>{tiles}</section>",
        f"<h2>Metrics present per {'SIC division' if grouped else 'company'} and year (%)</h2>",
        _table(["SIC division" if grouped else "Company", *years], heat_rows, "heat"),
        "<h2>Coverage by metric</h2>",
        _bars(metric_bars),
        "<h2>Trainable examples by history and horizon (quarters)</h2>",
        _table(["History", *[f"h = {h}" for h in HORIZONS]], example_rows),
        "<h2>Sectors</h2>",
        _table(["Sector", "Companies", "Names"], sector_rows),
        "<h2>Currency and reporting standard</h2>",
        _table(
            ["Dimension", "Values"],
            [
                ["Currency", _esc(", ".join(f"{k} {v}" for k, v in currencies.items()))],
                ["Standard", _esc(", ".join(f"{k} {v}" for k, v in standards.most_common()))],
            ],
        ),
        "<h2>Checks</h2>",
        _table(["Check", "Status", "Summary"], check_rows),
    ]
    viewport = '<meta name="viewport" content="width=device-width,initial-scale=1">'
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">{viewport}\n'
        f"<title>Gate B coverage</title><style>{CSS}</style></head>\n"
        "<body><main>\n" + "\n".join(sections) + "\n</main></body></html>\n"
    )


def write_gate(
    folder: Path,
    manifest: GateManifest,
    data: AuditData,
    examples: Sequence[Example],
    sectors: Sequence[SectorPriority],
    usable: dict[str, list[str]],
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    standards: Counter[str] = Counter(
        r.concept.split(":")[0] for rows in data.current.values() for r in rows if r.concept
    )
    (folder / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (folder / "examples.csv").write_text(examples_csv(examples), encoding="utf-8", newline="")
    (folder / "data-card.md").write_text(
        data_card(manifest, data, sectors, usable, standards), encoding="utf-8"
    )
    (folder / "coverage.html").write_text(
        coverage_html(manifest, data, sectors, standards), encoding="utf-8"
    )
    return folder
