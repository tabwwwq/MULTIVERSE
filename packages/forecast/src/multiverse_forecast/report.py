"""The benchmark report: JSON (``BenchmarkReport``), Markdown and HTML (Stage 15).

Written to ``var/data/forecast/<benchmark id>/`` (never committed). The tables show, per
target, MAE by horizon for every model with its change against persistence and the 95%
interval of that change, for all rows and for firms with material revenue; then
cold-start firms, weighting, sectors, the chosen settings, the largest errors and the
findings.
"""

import html
import json
from collections.abc import Sequence
from pathlib import Path

from multiverse_contracts.forecasting import (
    BenchmarkReport,
    ForecastTarget,
    Population,
    ScoreRow,
    SplitName,
)

MODELS = (
    "persistence",
    "seasonal_naive",
    "sector_average",
    "panel_ar",
    "ridge",
    "elastic_net",
    "gbm",
)
SPREAD = (
    "Model",
    "MAE",
    "95% interval",
    "Firm-weighted",
    "Revenue-weighted",
    "Median AE",
    "RMSE",
    "WAPE",
)
TITLES = {
    ForecastTarget.REVENUE_GROWTH: "Revenue growth (symmetric, year over year, -2 to 2)",
    ForecastTarget.OPERATING_MARGIN: "Operating margin (fraction of revenue)",
    ForecastTarget.EBITDA_MARGIN: "EBITDA margin (fraction of revenue)",
    ForecastTarget.FCF_MARGIN: "FCF margin (fraction of revenue)",
    ForecastTarget.DEBT_TO_EBITDA: "Debt / EBITDA (times)",
}
VIEWS = (
    ("Test: training firms, later origins, all rows", SplitName.TEST, Population.ALL),
    (
        "Test: firms with $10 million or more of revenue at the origin",
        SplitName.TEST,
        Population.MATERIAL,
    ),
    ("Cold start: firms never seen in training, all rows", SplitName.COLD_START, Population.ALL),
    (
        "Cold start: firms with $10 million or more of revenue at the origin",
        SplitName.COLD_START,
        Population.MATERIAL,
    ),
    ("Validation: chooses the settings, nothing else", SplitName.VALIDATION, Population.ALL),
)


def _row(
    report: BenchmarkReport,
    target: ForecastTarget,
    horizon: int,
    split: SplitName,
    model: str,
    population: Population = Population.ALL,
) -> ScoreRow | None:
    return next(
        (
            s
            for s in report.scores
            if s.target is target
            and s.horizon == horizon
            and s.split is split
            and s.model == model
            and s.population is population
        ),
        None,
    )


def _cell(s: ScoreRow | None) -> str:
    if s is None:
        return "-"
    if s.vs_naive is None or s.model == "persistence":
        return f"{s.mae:.4f}"
    marker = "*" if s.vs_naive_high is not None and s.vs_naive_high < 0 else ""
    return f"{s.mae:.4f} ({100 * s.vs_naive:+.1f}%{marker})"


def horizons(report: BenchmarkReport) -> list[int]:
    return sorted({s.horizon for s in report.scores})


def table(
    report: BenchmarkReport,
    target: ForecastTarget,
    split: SplitName,
    population: Population = Population.ALL,
) -> list[list[str]]:
    rows = []
    for horizon in horizons(report):
        cells = [_row(report, target, horizon, split, m, population) for m in MODELS]
        base = next((c for c in cells if c is not None), None)
        if base is None:
            continue
        rows.append(
            [f"h = {horizon}", str(base.examples), str(base.companies), *(_cell(c) for c in cells)]
        )
    return rows


def weighting(report: BenchmarkReport, target: ForecastTarget) -> list[list[str]]:
    rows = []
    for model in MODELS:
        s = _row(report, target, 4, SplitName.TEST, model)
        if s is not None:
            rows.append(
                [
                    model,
                    f"{s.mae:.4f}",
                    f"{s.mae_low:.4f} .. {s.mae_high:.4f}",
                    f"{s.firm_weighted_mae:.4f}",
                    f"{s.revenue_weighted_mae:.4f}",
                    f"{s.median_ae:.4f}",
                    f"{s.rmse:.4f}",
                    f"{s.wape:.3f}" if s.wape is not None else "-",
                ]
            )
    return rows


def sector_table(report: BenchmarkReport, target: ForecastTarget) -> list[list[str]]:
    rows = []
    mine = [
        s
        for s in report.sectors
        if s.target is target and s.horizon == 4 and s.split is SplitName.TEST
    ]
    for division in sorted({s.division for s in mine}):
        cells = {s.model: s for s in mine if s.division == division}
        examples = next(iter(cells.values())).examples
        rows.append(
            [
                division,
                str(examples),
                *(f"{cells[m].mae:.4f}" if m in cells else "-" for m in MODELS),
            ]
        )
    return rows


def _md(head: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|---" * len(head) + "|",
        *("| " + " | ".join(r) + " |" for r in rows),
        "",
    ]


def markdown(report: BenchmarkReport) -> str:
    head = ["Horizon", "Examples", "Firms", *MODELS]
    lines = [
        f"# Benchmark `{report.benchmark_id}`",
        "",
        f"Dataset `{report.dataset_id}` (SHA-256 `{report.dataset_sha256}`), protocol "
        f"`{report.protocol_id}` (SHA-256 `{report.protocol_sha256}`), seed {report.seed}.",
        "",
        "MAE per model; in brackets the change against persistence on the same rows, `*` when "
        "the 95% interval of that change (bootstrap over firms) lies below zero.",
        "",
        "## Findings",
        "",
        *(f"- {f}" for f in report.findings),
        "",
    ]
    for target in TITLES:
        if not any(s.target is target for s in report.scores):
            continue
        lines += [f"## {TITLES[target]}", ""]
        for title, split, population in VIEWS:
            lines += [f"{title}:", "", *_md(head, table(report, target, split, population))]
        lines += ["Test, h = 4: weighting and spread:", "", *_md(SPREAD, weighting(report, target))]
        lines += [
            "Test, h = 4: MAE by SIC division:",
            "",
            *_md(["Division", "Examples", *MODELS], sector_table(report, target)),
        ]
    settings = [
        [
            c.target.value,
            c.model,
            ", ".join(f"{p.name}={p.value}" for p in c.params) or "-",
            f"{c.validation_mae:.4f}" if c.validation_mae is not None else "-",
        ]
        for c in report.configs
    ]
    lines += ["## Settings chosen on validation", ""]
    lines += _md(["Target", "Model", "Settings", "Validation MAE"], settings)
    lines += ["## Largest errors (test, h = 4, best model)", ""]
    lines += [*(f"- {f}" for f in report.failures), ""]
    return "\n".join(lines)


CSS = """
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1f21;--muted:#5d6166;--line:#dcdcd6;--good:#2f7a4f}
@media (prefers-color-scheme: dark){:root{--bg:#141516;--panel:#1d1f21;--ink:#e8e8e3;
--muted:#a3a6aa;--line:#34373a;--good:#7ec79b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 8px}
h3{font-size:15px;margin:16px 0 6px}
.lede{color:var(--muted);margin:0 0 16px;overflow-wrap:anywhere}
.box{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600}
.better{color:var(--good);font-weight:600}
ul{padding-left:20px}li{margin:4px 0;overflow-wrap:anywhere}
"""


def _table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    th = "".join(f"<th>{html.escape(h)}</th>" for h in head)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td class='better'>{html.escape(c)}</td>"
            if c.endswith("*)")
            else f"<td>{html.escape(c)}</td>"
            for c in row
        )
        + "</tr>"
        for row in rows
    )
    return (
        f"<div class='box'><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def page(report: BenchmarkReport) -> str:
    head = ["Horizon", "Examples", "Firms", *MODELS]
    sections = [
        "<h1>Stage 15: forecasting baselines</h1>",
        f"<p class='lede'>Benchmark <code>{html.escape(report.benchmark_id)}</code> · dataset "
        f"<code>{html.escape(report.dataset_id)}</code> · protocol "
        f"<code>{html.escape(report.protocol_id)}</code> · seed {report.seed}. MAE per model; in "
        "brackets the change against persistence on the same rows, highlighted when its 95% "
        "interval (bootstrap over firms) lies below zero.</p>",
        "<h2>Findings</h2>",
        "<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in report.findings) + "</ul>",
    ]
    for target in TITLES:
        if not any(s.target is target for s in report.scores):
            continue
        sections.append(f"<h2>{html.escape(TITLES[target])}</h2>")
        for title, split, population in VIEWS:
            sections += [
                f"<h3>{html.escape(title)}</h3>",
                _table(head, table(report, target, split, population)),
            ]
        sections += [
            "<h3>Test, h = 4: weighting and spread</h3>",
            _table(SPREAD, weighting(report, target)),
            "<h3>Test, h = 4: MAE by SIC division</h3>",
            _table(["Division", "Examples", *MODELS], sector_table(report, target)),
        ]
    sections += [
        "<h2>Largest errors (test, h = 4, best model)</h2>",
        "<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in report.failures) + "</ul>",
    ]
    viewport = '<meta name="viewport" content="width=device-width,initial-scale=1">'
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">{viewport}\n'
        f"<title>Forecasting baselines</title><style>{CSS}</style></head>\n"
        "<body><main>\n" + "\n".join(sections) + "\n</main></body></html>\n"
    )


def write_report(report: BenchmarkReport, root: Path) -> Path:
    folder = root / report.benchmark_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_bytes(
        (json.dumps(report.model_dump(mode="json"), indent=2) + "\n").encode("utf-8")
    )
    (folder / "report.md").write_bytes(markdown(report).encode("utf-8"))
    (folder / "report.html").write_bytes(page(report).encode("utf-8"))
    return folder
