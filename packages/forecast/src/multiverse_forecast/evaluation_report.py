"""The Stage 17 evaluation package: scores, findings, tables and plots, from stored bands.

The trainings store their quantiles first (``bands``), so this step reruns in seconds and
a report that fails never costs a training. The package is named by the SHA-256 of its
scores and inputs; its findings keep every failure of the chosen model.
"""

import html
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from multiverse_contracts.forecasting import (
    AblationScore,
    ApprovalRow,
    BandScore,
    BenchmarkReport,
    CompanyErrors,
    EvaluationPackage,
    EvaluationProtocol,
    ForecastProtocol,
    MemorizationScore,
    Population,
    SliceScore,
    SplitName,
    StabilityScore,
)
from multiverse_contracts.primitives import ContractModel
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_forecast.bands import PARTIAL, Stored
from multiverse_forecast.data import Dataset, canonical_sha256
from multiverse_forecast.evaluation_plots import plots
from multiverse_forecast.evaluation_scores import (
    Entry,
    ablation_scores,
    approvals,
    band_scores,
    choose_primary,
    company_errors,
    entries_of,
    memorization_scores,
    scope_of,
    slice_scores,
    stability_scores,
)
from multiverse_forecast.report import CSS

ABLATION_PREFIX = "ablation_"


@dataclass(frozen=True)
class Measured:
    scores: list[BandScore]
    slices: list[SliceScore]
    companies: list[CompanyErrors]
    ablations: list[AblationScore]
    memorization: list[MemorizationScore]
    stability: list[StabilityScore]
    approvals: list[ApprovalRow]
    primary: str
    flag: bool
    choice: list[str]


def measure(
    dataset: Dataset, base: ForecastProtocol, protocol: EvaluationProtocol, stored: Stored
) -> Measured:
    scope = scope_of(dataset, base, protocol, stored)
    entries = entries_of(stored, scope, base)
    primary, flag, choice = choose_primary(scope, entries)
    scores = band_scores(scope, entries)
    entry, reference = entries[(primary, flag)], entries[("persistence", True)]
    raw = entries[(primary, False)]
    partner = Entry(primary, False, stored.bands[primary + PARTIAL].q.astype(np.float64))
    variants = {
        n.removeprefix(ABLATION_PREFIX): Entry(n, False, b.q.astype(np.float64))
        for n, b in stored.bands.items()
        if n.startswith(ABLATION_PREFIX) and not n.endswith(PARTIAL)
    }
    return Measured(
        scores=scores,
        slices=slice_scores(scope, entry, reference, stored.history, stored.outside),
        companies=company_errors(scope, entry, reference),
        ablations=ablation_scores(scope, partner, variants),
        memorization=memorization_scores(scope, raw, reference, stored.memory[primary]),
        stability=stability_scores(scope, raw, stored.medians[primary]),
        approvals=approvals(scope, scores, primary, flag),
        primary=primary,
        flag=flag,
        choice=choice,
    )


def _mean_gap(
    scores: list[BandScore], model: str, flag: bool, period: str, nominal: tuple[float, ...]
) -> list[float]:
    rows = [
        s
        for s in scores
        if s.model == model
        and s.calibrated is flag
        and s.period == period
        and s.split is SplitName.TEST
        and s.population is Population.ALL
    ]
    return [float(np.mean([abs(s.coverage[i] - n) for s in rows])) for i, n in enumerate(nominal)]


def findings(measured: Measured, protocol: EvaluationProtocol) -> tuple[list[str], list[str]]:
    primary, flag, nominal = measured.primary, measured.flag, protocol.nominal
    lines = [
        *measured.choice,
        f"chosen on the development years: {primary}, {'calibrated' if flag else 'not calibrated'}",
    ]
    for period in ("development", "final"):
        raw = _mean_gap(measured.scores, primary, False, period, nominal)
        fixed = _mean_gap(measured.scores, primary, True, period, nominal)
        lines.append(
            f"{period}: mean gap to nominal coverage "
            + "; ".join(
                f"{100 * n:.0f}% raw {a:.3f}, calibrated {b:.3f}"
                for n, a, b in zip(nominal, raw, fixed, strict=True)
            )
        )
    failures: list[str] = []
    rule = protocol.approval
    for s in measured.scores:
        if (
            s.model != primary
            or s.calibrated is not flag
            or s.population is not Population.ALL
            or s.period != "final"
        ):
            continue
        cover = ", ".join(
            f"{100 * n:.0f}%: {100 * c:.1f}%" for n, c in zip(nominal, s.coverage, strict=True)
        )
        rival = (
            f"{100 * (s.vs_best or 0):+.1f}% vs {s.best_baseline} "
            f"({100 * (s.vs_best_low or 0):+.1f}..{100 * (s.vs_best_high or 0):+.1f}%)"
        )
        lines.append(
            f"final years, {s.split.value}, {s.target.value} h={s.horizon}: {s.examples} rows, "
            f"coverage {cover}; pinball {s.pinball:.4g}, "
            f"{100 * (s.vs_persistence or 0):+.1f}% vs persistence "
            f"({100 * (s.vs_persistence_low or 0):+.1f}.."
            f"{100 * (s.vs_persistence_high or 0):+.1f}%), {rival}"
        )
        limit = rule.coverage_tolerance if s.split is SplitName.TEST else rule.cold_start_tolerance
        for n, c in zip(nominal, s.coverage, strict=True):
            if abs(c - n) > limit:
                failures.append(
                    f"final years, {s.split.value}, {s.target.value} h={s.horizon}: "
                    f"{100 * n:.0f}% interval covers {100 * c:.1f}% of {s.examples} rows"
                )
    approved = [a for a in measured.approvals if a.approved]
    lines.append(
        f"approval rule on the final years: {len(approved)} of {len(measured.approvals)} "
        "target and horizon pairs pass"
        + (
            ": " + ", ".join(f"{a.target.value} h={a.horizon}" for a in approved)
            if approved
            else ""
        )
    )
    for a in measured.approvals:
        if a.approved:
            continue
        missing = [
            name
            for name in (
                "enough_examples",
                "coverage_seen",
                "coverage_cold",
                "beats_persistence",
                "not_worse_than_best",
                "typical_firm",
            )
            if not getattr(a, name)
        ]
        failures.append(
            f"not approved: {a.target.value} h={a.horizon}, failed {', '.join(missing)}"
        )
    return lines, failures


def build(
    dataset: Dataset,
    sequences_id: str,
    protocol: EvaluationProtocol,
    protocol_sha256: str,
    benchmark: BenchmarkReport,
    measured: Measured,
    stored: Stored,
) -> EvaluationPackage:
    lines, failures = findings(measured, protocol)
    date = dataset.manifest.dataset_id.split("-")[1]
    model_hash = canonical_sha256(
        {
            "dataset": dataset.manifest.sha256,
            "protocol": protocol_sha256,
            "model": measured.primary,
            "calibrated": measured.flag,
            "checkpoints": stored.checkpoints[measured.primary],
        }
    )
    parts: dict[str, Sequence[ContractModel]] = {
        "scores": measured.scores,
        "slices": measured.slices,
        "companies": measured.companies,
        "ablations": measured.ablations,
        "memorization": measured.memorization,
        "stability": measured.stability,
        "approvals": measured.approvals,
    }
    payload: dict[str, object] = {
        "dataset": dataset.manifest.sha256,
        "protocol": protocol_sha256,
        "benchmark": benchmark.sha256,
        "bands": stored.sha256,
        "model": model_hash,
    }
    payload |= {k: [r.model_dump(mode="json") for r in v] for k, v in parts.items()}
    digest = canonical_sha256(payload)
    return EvaluationPackage(
        evaluation_id=f"eval-{date}-{digest[:12]}",
        sha256=digest,
        dataset_id=dataset.manifest.dataset_id,
        dataset_sha256=dataset.manifest.sha256,
        sequences_id=sequences_id,
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol_sha256,
        benchmark_id=benchmark.benchmark_id,
        bands_sha256=stored.sha256,
        model_id=f"model-{date}-{model_hash[:12]}",
        primary_model=measured.primary,
        calibrated=measured.flag,
        scores=tuple(measured.scores),
        slices=tuple(measured.slices),
        companies=tuple(measured.companies),
        ablations=tuple(measured.ablations),
        memorization=tuple(measured.memorization),
        stability=tuple(measured.stability),
        approvals=tuple(measured.approvals),
        findings=tuple(lines),
        failures=tuple(failures),
        contracts_version=CONTRACTS_VERSION,
        created_at=datetime.now(UTC),
    )


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:+.1f}%"


def _span(low: float | None, high: float | None) -> str:
    return "-" if low is None or high is None else f"{100 * low:+.1f}..{100 * high:+.1f}%"


def tables(
    package: EvaluationPackage, protocol: EvaluationProtocol
) -> list[tuple[str, list[str], list[list[str]]]]:
    """Every table of the report: a title, its head and its rows."""
    nominal = protocol.nominal
    names = ", ".join(f"{100 * n:.0f}%" for n in nominal)
    found: list[tuple[str, list[str], list[list[str]]]] = []
    for period in ("final", "development"):
        rows = [
            [
                s.model + (" (calibrated)" if s.calibrated else ""),
                s.split.value,
                s.target.value,
                str(s.horizon),
                str(s.examples),
                f"{s.pinball:.4g} ({s.pinball_low:.4g}..{s.pinball_high:.4g})",
                f"{s.wis:.4g}",
                _pct(s.vs_persistence)
                + " ("
                + _span(s.vs_persistence_low, s.vs_persistence_high)
                + ")",
                _pct(s.vs_best) + (f" vs {s.best_baseline}" if s.best_baseline else ""),
                ", ".join(f"{100 * c:.1f}" for c in s.coverage),
                ", ".join(f"{w:.3g}" for w in s.width),
                f"{s.median_ae:.3g}",
            ]
            for s in package.scores
            if s.period == period and s.population is Population.ALL
        ]
        found.append(
            (
                f"Bands on the {period} years",
                [
                    "Model",
                    "Split",
                    "Target",
                    "h",
                    "Rows",
                    "Pinball (95%)",
                    "WIS",
                    "vs persistence (95%)",
                    "vs best baseline",
                    f"Coverage % ({names})",
                    f"Mean width ({names})",
                    "Median AE",
                ],
                rows,
            )
        )
    found.append(
        (
            "Reliability: share of actuals below each quantile, final years, seen firms",
            ["Model", "Target", "h", *(f"{level}" for level in protocol.levels)],
            [
                [
                    s.model + (" (calibrated)" if s.calibrated else ""),
                    s.target.value,
                    str(s.horizon),
                    *(f"{v:.3f}" for v in s.reliability),
                ]
                for s in package.scores
                if s.period == "final"
                and s.split is SplitName.TEST
                and s.population is Population.ALL
                and s.model == package.primary_model
            ],
        )
    )
    found.append(
        (
            "Slices of the chosen model (seen firms, all test years)",
            [
                "Kind",
                "Value",
                "Target",
                "h",
                "Rows",
                "Firms",
                "Pinball",
                "vs persistence",
                f"Coverage % ({names})",
            ],
            [
                [
                    s.kind,
                    s.value,
                    s.target.value,
                    str(s.horizon),
                    str(s.examples),
                    str(s.companies),
                    f"{s.pinball:.4g}",
                    _pct(s.vs_persistence),
                    ", ".join(f"{100 * c:.1f}" for c in s.coverage),
                ]
                for s in package.slices
            ],
        )
    )
    found.append(
        (
            "Errors by firm (pinball of each firm's rows)",
            [
                "Target",
                "h",
                "Firms",
                "Rows",
                "Rows per firm (median)",
                "p10",
                "p50",
                "p90",
                "Firms better than persistence",
            ],
            [
                [
                    c.target.value,
                    str(c.horizon),
                    str(c.companies),
                    str(c.examples),
                    f"{c.examples_per_firm_median:.0f}",
                    f"{c.pinball_p10:.4g}",
                    f"{c.pinball_p50:.4g}",
                    f"{c.pinball_p90:.4g}",
                    f"{100 * c.better_than_persistence:.1f}%",
                ]
                for c in package.companies
            ],
        )
    )
    found.append(
        (
            "Ablations against the full model with the same seeds",
            ["Ablation", "Target", "h", "Rows", "Pinball", "Change (95%)"],
            [
                [
                    a.name,
                    a.target.value,
                    str(a.horizon),
                    str(a.examples),
                    f"{a.pinball:.4g}",
                    f"{_pct(a.change)} ({_span(a.change_low, a.change_high)})",
                ]
                for a in package.ablations
            ],
        )
    )
    found.append(
        (
            "Memorization: pinball where the model could remember a firm and where it could not",
            [
                "Target",
                "h",
                "Fitted rows",
                "Watch firms",
                "Test, seen firms",
                "Test, cold firms",
                "Cold over seen, each against persistence (95%)",
            ],
            [
                [
                    m.target.value,
                    str(m.horizon),
                    f"{m.trained:.4g}",
                    f"{m.watched:.4g}",
                    f"{m.test_seen:.4g}",
                    f"{m.test_cold:.4g}",
                    f"{_pct(m.cold_change)} ({_span(m.cold_change_low, m.cold_change_high)})",
                ]
                for m in package.memorization
            ],
        )
    )
    found.append(
        (
            "Stability: one quarter forecast from two origins, and between seeds",
            [
                "Target",
                "From h",
                "To h",
                "Pairs",
                "Median revision",
                "Median error of the later forecast",
                "Median spread between seeds",
            ],
            [
                [
                    s.target.value,
                    str(s.long_horizon),
                    str(s.short_horizon),
                    str(s.pairs),
                    f"{s.median_revision:.4g}",
                    f"{s.median_error:.4g}",
                    f"{s.median_seed_spread:.4g}",
                ]
                for s in package.stability
            ],
        )
    )
    found.append(
        (
            "Approval rule on the final years",
            [
                "Target",
                "h",
                "Rows",
                "Enough rows",
                "Coverage seen",
                "Coverage cold",
                "Beats persistence",
                "Not worse than best",
                "Typical firm",
                "Approved",
            ],
            [
                [
                    a.target.value,
                    str(a.horizon),
                    str(a.examples),
                    *(
                        "yes" if flag else "no"
                        for flag in (
                            a.enough_examples,
                            a.coverage_seen,
                            a.coverage_cold,
                            a.beats_persistence,
                            a.not_worse_than_best,
                            a.typical_firm,
                            a.approved,
                        )
                    ),
                ]
                for a in package.approvals
            ],
        )
    )
    return found


def markdown(package: EvaluationPackage, protocol: EvaluationProtocol) -> str:
    lines = [
        f"# Stage 17 evaluation `{package.evaluation_id}`",
        "",
        f"Model `{package.model_id}` ({package.primary_model}, "
        f"{'calibrated' if package.calibrated else 'not calibrated'}). Dataset "
        f"`{package.dataset_id}`, sequences `{package.sequences_id}`, protocol "
        f"`{package.protocol_id}` (SHA-256 `{package.protocol_sha256}`), settings of "
        f"`{package.benchmark_id}`. Scores are in each target's training space.",
        "",
        "## Findings",
        "",
        *(f"- {f}" for f in package.findings),
        "",
        "## Failures",
        "",
        *(f"- {f}" for f in package.failures),
        "",
    ]
    for title, head, rows in tables(package, protocol):
        lines += [
            f"## {title}",
            "",
            "| " + " | ".join(head) + " |",
            "|---" * len(head) + "|",
            *("| " + " | ".join(r) + " |" for r in rows),
            "",
        ]
    return "\n".join(lines)


def page(package: EvaluationPackage, protocol: EvaluationProtocol) -> str:
    viewport = '<meta name="viewport" content="width=device-width,initial-scale=1">'
    blocks = []
    for title, head, rows in tables(package, protocol):
        th = "".join(f"<th>{html.escape(h)}</th>" for h in head)
        body = "".join(
            "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in rows
        )
        blocks.append(
            f"<h2>{html.escape(title)}</h2><div class='box'><table><thead><tr>{th}</tr></thead>"
            f"<tbody>{body}</tbody></table></div>"
        )
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">{viewport}\n'
        f"<title>Model evaluation</title><style>{CSS}</style></head>\n<body><main>\n"
        "<h1>Stage 17: what the quantile forecasts are worth</h1>"
        f"<p class='lede'>Evaluation <code>{html.escape(package.evaluation_id)}</code> · model "
        f"<code>{html.escape(package.model_id)}</code> · dataset "
        f"<code>{html.escape(package.dataset_id)}</code>.</p>"
        "<h2>Findings</h2><ul>"
        + "".join(f"<li>{html.escape(f)}</li>" for f in package.findings)
        + "</ul><h2>Failures</h2><ul>"
        + "".join(f"<li>{html.escape(f)}</li>" for f in package.failures)
        + "</ul>"
        + "".join(blocks)
        + "\n</main></body></html>\n"
    )


def write(
    package: EvaluationPackage, protocol: EvaluationProtocol, root: Path, figures: Path | None
) -> Path:
    folder = root / package.evaluation_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_bytes(
        (json.dumps(package.model_dump(mode="json"), indent=2) + "\n").encode("utf-8")
    )
    (folder / "report.md").write_bytes(markdown(package, protocol).encode("utf-8"))
    (folder / "report.html").write_bytes(page(package, protocol).encode("utf-8"))
    for target_folder in (folder, figures):
        if target_folder is None:
            continue
        target_folder.mkdir(parents=True, exist_ok=True)
        for name, text in plots(package, protocol).items():
            (target_folder / name).write_bytes(text.encode("utf-8"))
    return folder
