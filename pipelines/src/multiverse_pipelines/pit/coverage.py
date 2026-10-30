"""The financial coverage dashboard of an as-of panel (DATA-05, docs/11 honest metrics).

Explicit counts, never estimates: for each metric, how many firm-quarters of the window
hold a value at the cutoff and why the others are empty; the same per company and per
quarter; how coverage grew from one year-end cutoff to the next; how often values were
revised after they were first public; and the chronology alerts.

Written next to the warehouse (``var/data/pit/coverage/``, never committed) as
``coverage.json``, ``coverage.md`` and a self-contained ``coverage.html``.
"""

import html
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.normalized import Revision
from multiverse_contracts.pit import (
    MASKED_STATES,
    CellState,
    ChronologyAlert,
    KnowledgeView,
    PanelCell,
    ValueChange,
)
from multiverse_pipelines.pit.clock import day_end, eastern_date
from multiverse_pipelines.pit.panel import PANEL_METRICS, build_panel
from multiverse_pipelines.pit.warehouse import Warehouse

STATE_LABELS = {
    CellState.OBSERVED: "Observed",
    CellState.DERIVED: "Derived",
    CellState.NOT_YET_FILED: "Not yet filed",
    CellState.NOT_REPORTED: "Not reported",
    CellState.BLOCKED: "Blocked",
    CellState.INACTIVE: "Inactive",
    CellState.NOT_COVERED: "Not covered",
}
STATE_HELP = {
    CellState.OBSERVED: "reported for the quarter by a filing public at the cutoff",
    CellState.DERIVED: "computed from reported values that were all public at the cutoff",
    CellState.NOT_YET_FILED: "the quarter ended, its 10-Q or 10-K was not public yet",
    CellState.NOT_REPORTED: "the report was public, without this metric",
    CellState.BLOCKED: "withheld: conflicting values in one filing",
    CellState.INACTIVE: "a Form 15 with no report after it, the next report overdue",
    CellState.NOT_COVERED: "before the company's first XBRL report",
}


@dataclass
class Coverage:
    cutoff_label: str
    cutoff: datetime
    view: KnowledgeView
    quarters: int
    names: Mapping[str, str]
    cells: Sequence[PanelCell]
    over_time: list[dict[str, Any]] = field(default_factory=list)
    revisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    alerts: Sequence[ChronologyAlert] = ()

    def by(self, key: str) -> dict[str, Counter[CellState]]:
        found: dict[str, Counter[CellState]] = defaultdict(Counter)
        for cell in self.cells:
            found[getattr(cell, key)][cell.state] += 1
        return dict(found)

    def grid(self) -> dict[tuple[str, str], int]:
        found: Counter[tuple[str, str]] = Counter()
        for cell in self.cells:
            found[(cell.cik, cell.calendar_quarter)] += int(cell.mask)
        return dict(found)


def share(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{100 * part / whole:.1f}%"


def coverage_over_time(
    warehouse: Warehouse, ciks: Sequence[str], last: date, view: KnowledgeView, quarters: int
) -> list[dict[str, Any]]:
    """Year-end cutoffs from 2009 to the last one: masked cells of the window."""
    rows: list[dict[str, Any]] = []
    for year in range(2009, last.year + 1):
        cutoff = day_end(min(date(year, 12, 31), last))
        cells = build_panel(warehouse, ciks, cutoff, view=view, quarters=quarters).cells
        counts = Counter(cell.state for cell in cells)
        masked = sum(counts[s] for s in MASKED_STATES)
        public = masked + counts[CellState.NOT_REPORTED] + counts[CellState.BLOCKED]
        rows.append(
            {
                "cutoff": eastern_date(cutoff).isoformat(),
                "cells": len(cells),
                "masked": masked,
                "public_reports": public,
                **{state.value: counts[state] for state in CellState},
            }
        )
    return rows


def revision_stats(warehouse: Warehouse, ciks: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Per metric: values revised after they were first public, and by how much."""
    revised: dict[str, list[Decimal]] = defaultdict(list)
    confirmed: Counter[str] = Counter()
    for cik in ciks:
        previous: dict[tuple[str, int, str], str | None] = {}
        for item in warehouse.all_values(cik):
            row = item.value
            if row.revision is not Revision.LATEST:
                continue
            key = (row.metric, row.fiscal_year, row.fiscal_period.value)
            before = previous.get(key)
            if item.change is ValueChange.VALUE_REVISED and before and row.value:
                old, new = Decimal(before), Decimal(row.value)
                if old != 0:
                    revised[row.metric].append(abs(new - old) / abs(old))
            elif item.change is ValueChange.CONFIRMED:
                confirmed[row.metric] += 1
            previous[key] = row.value
    stats: dict[str, dict[str, Any]] = {}
    for metric in PANEL_METRICS:
        changes = revised.get(metric, [])
        stats[metric] = {
            "revised": len(changes),
            "confirmed": confirmed[metric],
            "median_change": f"{100 * statistics.median(changes):.2f}%" if changes else "n/a",
        }
    return stats


def to_json(report: Coverage) -> dict[str, Any]:
    return {
        "cutoff": report.cutoff_label,
        "view": report.view.value,
        "quarters": report.quarters,
        "companies": len(report.names),
        "cells": len(report.cells),
        "by_metric": {
            m: {s.value: n for s, n in c.items()} for m, c in report.by("metric").items()
        },
        "by_company": {k: {s.value: n for s, n in c.items()} for k, c in report.by("cik").items()},
        "over_time": report.over_time,
        "revisions": report.revisions,
        "alerts": Counter(f"{a.kind.value}/{a.severity.value}" for a in report.alerts),
    }


def _state_row(label: str, counts: Counter[CellState], total: int) -> str:
    masked = sum(counts[s] for s in MASKED_STATES)
    cells = " | ".join(str(counts[s]) for s in CellState)
    return f"| {label} | {masked} of {total} ({share(masked, total)}) | {cells} |"


def to_markdown(report: Coverage) -> str:
    states = " | ".join(STATE_LABELS[s] for s in CellState)
    lines = [
        f"# PIT coverage at {report.cutoff_label} ({report.view.value} view)",
        "",
        f"{len(report.names)} companies, last {report.quarters} calendar quarters, "
        f"{len(PANEL_METRICS)} metrics: {len(report.cells)} firm-quarter-metric cells.",
        "",
        "## By metric (firm-quarters with a value)",
        "",
        f"| metric | with value | {states} |",
        "|---|---|" + "---|" * len(CellState),
    ]
    by_metric = report.by("metric")
    for metric in PANEL_METRICS:
        counts = by_metric.get(metric, Counter())
        lines.append(_state_row(metric, counts, sum(counts.values())))
    lines += ["", "## By company", "", f"| company | with value | {states} |"]
    lines.append("|---|---|" + "---|" * len(CellState))
    for cik, counts in sorted(report.by("cik").items()):
        lines.append(_state_row(f"{report.names.get(cik, cik)}", counts, sum(counts.values())))
    if report.over_time:
        lines += ["", "## Year-end cutoffs (same window)", ""]
        lines += [
            "| cutoff | with value | public reports | not yet filed | inactive |",
            "|---|---|---|---|---|",
        ]
        for row in report.over_time:
            lines.append(
                f"| {row['cutoff']} | {row['masked']} of {row['cells']} "
                f"({share(row['masked'], row['cells'])}) | {row['public_reports']} | "
                f"{row['not_yet_filed']} | {row['inactive']} |"
            )
    lines += [
        "",
        "## Revisions after first public",
        "",
        "| metric | revised | confirmed | median change |",
    ]
    lines.append("|---|---|---|---|")
    for metric, stats in report.revisions.items():
        lines.append(
            f"| {metric} | {stats['revised']} | {stats['confirmed']} | {stats['median_change']} |"
        )
    alerts = Counter((a.kind.value, a.severity.value) for a in report.alerts)
    lines += ["", "## Chronology alerts", "", "| alert | severity | count |", "|---|---|---|"]
    for (kind, severity), count in sorted(alerts.items()):
        lines.append(f"| {kind} | {severity} | {count} |")
    lines += ["", "States: " + "; ".join(f"{STATE_LABELS[s]}: {STATE_HELP[s]}" for s in CellState)]
    return "\n".join(lines) + "\n"


CSS = """

:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1f21;--muted:#5d6166;--line:#dcdcd6;--accent:#2f5d8a;
--good:#2f7a4f;--warn:#9a6a00;--bad:#a33b3b;--cell0:#eceae4}
@media (prefers-color-scheme: dark){:root{--bg:#141516;--panel:#1d1f21;--ink:#e8e8e3;
--muted:#a3a6aa;--line:#34373a;--accent:#8db6df;--good:#7ec79b;--warn:#e0b45c;--bad:#e48a8a;
--cell0:#26282b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}h1{font-size:24px;margin:0 0 4px}
h2{font-size:18px;margin:32px 0 8px}p.lede{color:var(--muted);margin:0 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:13px}
.scroll{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--panel)}
th{color:var(--muted);font-weight:600}
.bar{display:inline-block;height:8px;background:var(--accent);border-radius:2px;
vertical-align:middle;margin-right:6px}
.grid td{text-align:center;min-width:34px}.note{color:var(--muted);font-size:13px}
.sev-blocking{color:var(--bad)}.sev-warning{color:var(--warn)}
.wrap{text-align:left;white-space:normal}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;font-size:13px}
dt{font-weight:600}
"""


def _esc(text: object) -> str:
    return html.escape(str(text))


def _counts_table(rows: list[tuple[str, Counter[CellState]]]) -> str:
    head = "".join(f"<th>{_esc(STATE_LABELS[s])}</th>" for s in CellState)
    body = []
    for label, counts in rows:
        total = sum(counts.values())
        masked = sum(counts[s] for s in MASKED_STATES)
        width = 0 if total == 0 else round(80 * masked / total)
        cells = "".join(f"<td>{counts[s]}</td>" for s in CellState)
        body.append(
            f"<tr><td>{_esc(label)}</td><td><span class=bar style='width:{width}px'></span>"
            f"{masked} / {total} ({share(masked, total)})</td>{cells}</tr>"
        )
    return (
        f"<div class=scroll><table><thead><tr><th>&nbsp;</th><th>With value</th>{head}</tr>"
        f"</thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def to_html(report: Coverage, *, snapshot_id: str | None = None) -> str:
    total = len(report.cells)
    counts = Counter(cell.state for cell in report.cells)
    masked = sum(counts[s] for s in MASKED_STATES)
    severities = Counter(a.severity for a in report.alerts)
    kpis = [
        (f"{masked:,}", f"cells with a value of {total:,} ({share(masked, total)})"),
        (f"{counts[CellState.NOT_YET_FILED]:,}", "not yet filed at the cutoff"),
        (f"{counts[CellState.NOT_REPORTED]:,}", "report public, metric not in it"),
        (f"{counts[CellState.INACTIVE]:,}", "inactive (deregistered)"),
        (f"{severities[QualitySeverity.BLOCKING]}", "blocking chronology alerts"),
        (f"{severities[QualitySeverity.WARNING]}", "warnings"),
    ]
    by_metric = report.by("metric")
    metric_rows = [(m, by_metric.get(m, Counter())) for m in PANEL_METRICS]
    company_rows = [(report.names.get(c, c), n) for c, n in sorted(report.by("cik").items())]
    quarters = sorted({c.calendar_quarter for c in report.cells})
    grid = report.grid()
    per_cell = len(PANEL_METRICS)
    grid_rows = []
    for cik in sorted({c.cik for c in report.cells}):
        tds = []
        for quarter in quarters:
            value = grid.get((cik, quarter), 0)
            alpha = 0.12 + 0.88 * value / per_cell if value else 0
            style = (
                f"background:rgba(47,122,79,{alpha:.2f})" if value else "background:var(--cell0)"
            )
            tds.append(
                f"<td style='{style}' title='{_esc(quarter)}: {value} of {per_cell}'>{value}</td>"
            )
        grid_rows.append(f"<tr><td>{_esc(report.names.get(cik, cik))}</td>{''.join(tds)}</tr>")
    grid_head = "".join(f"<th>{_esc(q[2:])}</th>" for q in quarters)
    time_rows = "".join(
        f"<tr><td>{_esc(r['cutoff'])}</td><td><span class=bar style='width:"
        f"{0 if not r['cells'] else round(120 * r['masked'] / r['cells'])}px'></span>"
        f"{r['masked']} / {r['cells']} ({share(r['masked'], r['cells'])})</td>"
        f"<td>{r['not_yet_filed']}</td><td>{r['not_covered']}</td><td>{r['inactive']}</td></tr>"
        for r in report.over_time
    )
    revision_rows = "".join(
        f"<tr><td>{_esc(m)}</td><td>{s['revised']}</td><td>{s['confirmed']}</td>"
        f"<td>{_esc(s['median_change'])}</td></tr>"
        for m, s in report.revisions.items()
    )
    alert_counts = Counter((a.kind.value, a.severity.value) for a in report.alerts)
    alert_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td class='sev-{s}'>{_esc(s)}</td><td>{n}</td></tr>"
        for (k, s), n in sorted(alert_counts.items())
    )
    serious = [a for a in report.alerts if a.severity is not QualitySeverity.INFO][:40]
    serious_rows = "".join(
        f"<tr><td>{_esc(report.names.get(a.cik, a.cik))}</td>"
        f"<td class='sev-{a.severity.value}'>{_esc(a.kind.value)}</td>"
        f"<td class=wrap>{_esc(a.detail)}</td></tr>"
        for a in serious
    )
    legend = "".join(
        f"<dt>{_esc(STATE_LABELS[s])}</dt><dd>{_esc(STATE_HELP[s])}</dd>" for s in CellState
    )
    snap = f" · snapshot <code>{_esc(snapshot_id)}</code>" if snapshot_id else ""
    tiles = "".join(f"<div class=kpi><b>{v}</b><span>{_esc(t)}</span></div>" for v, t in kpis)
    lede = (
        f"{_esc(report.view.value.capitalize())} view{snap} · {len(report.names)} companies of "
        f"the SEC sample (decision D-09) · last {report.quarters} calendar quarters · "
        f"{per_cell} metrics. Counts are measured on the local archive; nothing is estimated."
    )
    viewport = '<meta name="viewport" content="width=device-width,initial-scale=1">'
    sections = [
        f"<h1>Point-in-time coverage at {_esc(report.cutoff_label)}</h1>",
        f"<p class=lede>{lede}</p>",
        f"<section class=kpis>{tiles}</section>",
        f"<h2>By metric</h2>{_counts_table(metric_rows)}",
        f"<h2>By company</h2>{_counts_table(company_rows)}",
        "<h2>Metrics with a value per firm-quarter</h2>",
        _table(["&nbsp;"], grid_rows, head_html=grid_head, extra="grid"),
        f"<p class=note>Each cell counts metrics with a value at the cutoff, of {per_cell}.</p>",
        "<h2>Year-end cutoffs</h2>",
        _table(
            ["Cutoff", "With value (same window)", "Not yet filed", "Not covered", "Inactive"],
            [time_rows],
        ),
        "<h2>Revisions after first public</h2>",
        _table(
            ["Metric", "Revised", "Confirmed by a later filing", "Median change"], [revision_rows]
        ),
        "<h2>Chronology alerts</h2>",
        _table(["Alert", "Severity", "Count"], [alert_rows]),
        "<h2>Warnings and blocking alerts</h2>",
        _table(["Company", "Alert", "Detail"], [serious_rows]),
        f"<h2>States</h2><dl>{legend}</dl>",
    ]
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">{viewport}\n'
        f"<title>PIT coverage {_esc(report.cutoff_label)}</title><style>{CSS}</style></head>\n"
        "<body><main>\n" + "\n".join(sections) + "\n</main></body></html>\n"
    )


def _table(
    head: Sequence[str], rows: Sequence[str], *, head_html: str = "", extra: str = ""
) -> str:
    cells = "".join(f"<th>{h}</th>" for h in head) + head_html
    return (
        f"<div class='scroll {extra}'><table><thead><tr>{cells}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def write_coverage(report: Coverage, folder: Path, *, snapshot_id: str | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "coverage.json").write_text(
        json.dumps(to_json(report), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (folder / "coverage.md").write_text(to_markdown(report), encoding="utf-8")
    (folder / "coverage.html").write_text(
        to_html(report, snapshot_id=snapshot_id), encoding="utf-8"
    )
    return folder
