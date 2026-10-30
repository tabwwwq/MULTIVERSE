"""The Gate B checks over the point-in-time warehouse (prompt 14 audit checklist).

Each check measures one risk on the data as it is and returns a status:

- ``pass``: nothing found, or only what the pipeline already guards against;
- ``warning``: something a model or a reader must know, with the cases;
- ``fail``: the data contradicts itself or the pipeline;
- ``blocked``: the data cannot support the next step yet (size, missing sources).
"""

import itertools
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.normalized import FiscalPeriod, NormalizedValue, QualityFlag, Revision
from multiverse_contracts.pit import MASKED_STATES, CellState, ChronologyAlert, ValueChange
from multiverse_contracts.quality import CheckStatus, GateCheck, Measure
from multiverse_contracts.sources import CompanyCandidate
from multiverse_pipelines.pit.panel import Panel, nearest_quarter_end, quarter_label
from multiverse_pipelines.pit.warehouse import Warehouse

CORE = ("revenue", "operating_income", "net_income", "cfo", "capex", "cash")
FLOWS = ("revenue", "operating_income", "cfo")
QUARTERS = (FiscalPeriod.Q1, FiscalPeriod.Q2, FiscalPeriod.Q3, FiscalPeriod.Q4)
JUMP = Decimal("0.5")
OUTLIER_Z = 6.0
SUM_TOLERANCE = Decimal("0.005")
MISSING_WARN = 0.25


@dataclass
class AuditData:
    warehouse: Warehouse
    ciks: list[str]
    names: dict[str, str]
    candidates: dict[str, CompanyCandidate]
    data_cutoff: datetime
    panel: Panel
    current: dict[str, list[NormalizedValue]] = field(default_factory=dict)
    alerts: list[ChronologyAlert] = field(default_factory=list)
    revised: Counter[str] = field(default_factory=Counter)
    bankruptcy_filings: list[str] = field(default_factory=list)
    """8-K filings with item 1.03 (bankruptcy or receivership), from the archived index."""

    def name(self, cik: str) -> str:
        return self.names.get(cik, cik)


def load(
    warehouse: Warehouse,
    ciks: Sequence[str],
    names: dict[str, str],
    candidates: dict[str, CompanyCandidate],
    data_cutoff: datetime,
    panel: Panel,
) -> AuditData:
    mine = {cik: candidates[cik] for cik in ciks if cik in candidates}
    data = AuditData(warehouse, list(ciks), names, mine, data_cutoff, panel)
    for cik in ciks:
        rows = []
        for item in warehouse.all_values(cik):
            if item.value.revision is not Revision.LATEST:
                continue
            if item.change is ValueChange.VALUE_REVISED:
                data.revised[item.value.metric] += 1
            if item.known_to is None:
                rows.append(item.value)
        data.current[cik] = rows
    data.alerts = warehouse.alerts(ciks)
    return data


def _quarterly(
    data: AuditData, metric: str
) -> dict[str, dict[tuple[int, FiscalPeriod], NormalizedValue]]:
    found: dict[str, dict[tuple[int, FiscalPeriod], NormalizedValue]] = {}
    for cik, rows in data.current.items():
        found[cik] = {(r.fiscal_year, r.fiscal_period): r for r in rows if r.metric == metric}
    return found


def _series(data: AuditData, cik: str, metric: str) -> list[tuple[str, Decimal]]:
    """Quarterly values of one metric as known today, oldest first, by calendar quarter."""
    rows = [
        r
        for r in data.current[cik]
        if r.metric == metric and r.fiscal_period in QUARTERS and r.value is not None
    ]
    rows.sort(key=lambda r: r.period_end)
    return [
        (quarter_label(nearest_quarter_end(r.period_end)), Decimal(r.value or "0")) for r in rows
    ]


def _check(
    check_id: str,
    title: str,
    status: CheckStatus,
    summary: str,
    measures: dict[str, object] | None = None,
    findings: Sequence[str] = (),
    companies: Sequence[str] = (),
) -> GateCheck:
    return GateCheck(
        check_id=check_id,
        title=title,
        status=status,
        summary=summary,
        measures=tuple(
            Measure(name=k, value=str(v) or "none") for k, v in (measures or {}).items()
        ),
        findings=tuple(findings[:40]),
        companies=tuple(sorted(set(companies))),
    )


def future_revisions(data: AuditData) -> GateCheck:
    total = sum(data.revised.values())
    top = ", ".join(f"{m} {n}" for m, n in data.revised.most_common(5))
    return _check(
        "future_revisions",
        "Future revisions",
        CheckStatus.PASS,
        f"{total} values were revised after their first release; panels use the vintage known "
        "at each origin, so none of these revisions reaches an earlier origin",
        {"revisions after first release": total, "most revised": top or "none"},
    )


def duplicated_company_quarters(data: AuditData) -> GateCheck:
    findings: list[str] = []
    for cik, rows in data.current.items():
        slots: Counter[tuple[str, str]] = Counter(
            (r.metric, quarter_label(nearest_quarter_end(r.period_end)))
            for r in rows
            if r.fiscal_period in QUARTERS and r.value is not None
        )
        findings += [f"{data.name(cik)}: {m} {q} twice" for (m, q), n in slots.items() if n > 1]
    cells = Counter((c.cik, c.calendar_quarter, c.metric) for c in data.panel.cells)
    repeated = sum(1 for n in cells.values() if n > 1)
    status = CheckStatus.PASS if not findings and not repeated else CheckStatus.FAIL
    return _check(
        "duplicated_company_quarter",
        "Duplicated company-quarters",
        status,
        "one value per company, calendar quarter and metric"
        if status is CheckStatus.PASS
        else "two fiscal quarters fall into one calendar quarter",
        {"panel cells repeated": repeated, "fiscal quarters colliding": len(findings)},
        findings,
    )


def concept_drift(data: AuditData) -> GateCheck:
    findings: list[str] = []
    companies: list[str] = []
    switches = 0
    for cik, rows in data.current.items():
        by_metric: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for r in rows:
            if r.fiscal_period is FiscalPeriod.FY and r.concept:
                by_metric[r.metric].append((r.fiscal_year, r.concept))
        for metric, years in by_metric.items():
            years.sort()
            for (y1, c1), (y2, c2) in itertools.pairwise(years):
                if c1 != c2:
                    switches += 1
                    companies.append(cik)
                    if len(findings) < 40:
                        findings.append(
                            f"{data.name(cik)} {metric}: {c1.split(':')[1]} (FY{y1}) to "
                            f"{c2.split(':')[1]} (FY{y2})"
                        )
    disagreements = sum(
        QualityFlag.CONCEPT_DISAGREEMENT in r.flags for rows in data.current.values() for r in rows
    )
    return _check(
        "concept_drift",
        "Concept drift",
        CheckStatus.WARNING if switches or disagreements else CheckStatus.PASS,
        "concepts change between fiscal years (one concept per year, never mixed in a quarter); "
        "equivalent concepts disagreeing by more than 0.5% are flagged",
        {"concept switches": switches, "values flagged concept_disagreement": disagreements},
        findings,
        companies,
    )


def survivorship(data: AuditData) -> GateCheck:
    acquired = [c for c in data.candidates.values() if c.status == "acquired"]
    listed = [c for c in data.candidates.values() if c.status == "listed"]
    return _check(
        "survivor_only_sample",
        "Survivor-only sample",
        CheckStatus.WARNING,
        f"{len(listed)} of {len(data.candidates)} companies are listed today; the sample was "
        "chosen in 2026 by a rubric, not drawn from the population of filers at each date",
        {"listed today": len(listed), "acquired or deregistered": len(acquired)},
        [f"{c.name}: {c.status}" for c in acquired]
        + ["companies that failed, shrank or were never large are absent by construction"],
        [c.cik for c in acquired],
    )


def bankruptcies(data: AuditData) -> GateCheck:
    deregistered = [a for a in data.alerts if a.kind.value == "deregistration"]
    return _check(
        "lost_bankruptcies",
        "Lost bankruptcies",
        CheckStatus.WARNING,
        f"{len(data.bankruptcy_filings)} bankruptcy filings (8-K item 1.03) and "
        f"{len(deregistered)} deregistrations in the sample; a model trained here has not seen "
        "a failing company",
        {
            "bankruptcies (8-K item 1.03)": len(data.bankruptcy_filings),
            "deregistrations": len(deregistered),
        },
        [f"{data.name(a.cik)}: {a.detail}" for a in deregistered] + data.bankruptcy_filings,
        [a.cik for a in deregistered],
    )


def missingness(data: AuditData) -> GateCheck:
    by_metric: dict[str, Counter[CellState]] = defaultdict(Counter)
    for cell in data.panel.cells:
        by_metric[cell.metric][cell.state] += 1
    measures: dict[str, object] = {}
    findings: list[str] = []
    worst = 0.0
    for metric, counts in sorted(by_metric.items()):
        expected = (
            sum(counts.values())
            - counts[CellState.INACTIVE]
            - counts[CellState.NOT_COVERED]
            - counts[CellState.NOT_YET_FILED]
        )
        masked = sum(counts[s] for s in MASKED_STATES)
        share = 1 - masked / expected if expected else 1.0
        measures[f"{metric} missing"] = f"{100 * share:.1f}% of {expected}"
        if metric in CORE:
            worst = max(worst, share)
        if share > MISSING_WARN:
            findings.append(f"{metric}: {100 * share:.1f}% missing where a report was public")
    return _check(
        "missingness",
        "Missingness",
        CheckStatus.WARNING if findings else CheckStatus.PASS,
        f"share of company-quarters without a value where the report was public; the worst "
        f"core metric misses {100 * worst:.1f}%",
        measures,
        findings,
    )


def revenue_gaps(data: AuditData) -> GateCheck:
    findings: list[str] = []
    companies: list[str] = []
    for cik in data.ciks:
        cells = sorted(
            (c for c in data.panel.cells if c.cik == cik and c.metric == "revenue"),
            key=lambda c: c.quarter_end,
        )
        present = [i for i, c in enumerate(cells) if c.mask]
        if not present:
            continue
        holes = [cells[i] for i in range(present[0], present[-1] + 1) if not cells[i].mask]
        if holes:
            companies.append(cik)
            labels = ", ".join(c.calendar_quarter for c in holes[:6])
            findings.append(f"{data.name(cik)}: {len(holes)} quarters without revenue ({labels})")
    return _check(
        "revenue_gaps",
        "Revenue gaps",
        CheckStatus.WARNING if findings else CheckStatus.PASS,
        "quarters without revenue between a company's first and last revenue quarter",
        {"companies with gaps": len(companies)},
        findings,
        companies,
    )


def ratios(data: AuditData) -> GateCheck:
    revenue = _quarterly(data, "revenue")
    undefined = negative_revenue = 0
    findings: list[str] = []
    for metric in ("operating_income", "free_cash_flow", "capex", "rnd"):
        values = _quarterly(data, metric)
        for cik, rows in values.items():
            for key, row in rows.items():
                if row.value is None or key[1] is FiscalPeriod.FY:
                    continue
                base = revenue[cik].get(key)
                if base is None or base.value is None or Decimal(base.value) <= 0:
                    undefined += 1
                    if base is not None and base.value is not None and Decimal(base.value) < 0:
                        negative_revenue += 1
    capex = _quarterly(data, "capex")
    negative_capex = [
        f"{data.name(cik)} capex FY{y} {p.value}: {r.value}"
        for cik, rows in capex.items()
        for (y, p), r in rows.items()
        if r.value is not None and Decimal(r.value) < 0
    ]
    findings += negative_capex
    return _check(
        "negative_undefined_ratios",
        "Negative and undefined ratios",
        CheckStatus.WARNING if negative_capex or negative_revenue else CheckStatus.PASS,
        "margins and intensities over revenue: undefined when revenue is missing or not "
        "positive; never computed with a zero",
        {
            "ratio inputs without positive revenue": undefined,
            "negative revenue": negative_revenue,
            "negative capex quarters": len(negative_capex),
        },
        findings,
    )


def currency(data: AuditData) -> GateCheck:
    currencies = Counter(r.currency for rows in data.current.values() for r in rows if r.currency)
    non_usd = sum(n for c, n in currencies.items() if c != "USD")
    return _check(
        "currency_fx",
        "Currency and FX conversion",
        CheckStatus.PASS if non_usd == 0 else CheckStatus.WARNING,
        "every money value is in its reporting currency; no FX conversion is done",
        {
            "currencies": ", ".join(f"{c} {n}" for c, n in currencies.items()),
            "non-USD values": non_usd,
        },
    )


def _changes(data: AuditData) -> list[tuple[str, str, str, float]]:
    found = []
    for cik in data.ciks:
        for metric in FLOWS:
            series = _series(data, cik, metric)
            for (_, a), (label, b) in itertools.pairwise(series):
                if a > 0 and b > 0:
                    found.append((cik, metric, label, math.log(float(b / a))))
    return found


def outliers(data: AuditData) -> GateCheck:
    changes = _changes(data)
    findings: list[str] = []
    by_key: dict[tuple[str, str], list[float]] = defaultdict(list)
    for cik, metric, _, change in changes:
        by_key[(cik, metric)].append(change)
    flagged = 0
    for cik, metric, label, change in changes:
        values = by_key[(cik, metric)]
        median = statistics.median(values)
        mad = statistics.median(abs(v - median) for v in values) or 1e-9
        z = 0.6745 * (change - median) / mad
        if abs(z) > OUTLIER_Z:
            flagged += 1
            findings.append(
                f"{data.name(cik)} {metric} {label}: log change {change:+.2f}, robust z {z:+.1f}"
            )
    return _check(
        "outliers",
        "Outliers",
        CheckStatus.WARNING if flagged else CheckStatus.PASS,
        f"quarter-to-quarter log changes with a robust z-score above {OUTLIER_Z:g} per company "
        "and metric (positive values only)",
        {"changes examined": len(changes), "outliers": flagged},
        findings,
    )


def jumps(data: AuditData) -> GateCheck:
    findings: list[str] = []
    companies: list[str] = []
    for cik in data.ciks:
        series = _series(data, cik, "revenue")
        for (_, a), (label, b) in itertools.pairwise(series):
            if a > 0 and abs(b / a - 1) > JUMP:
                companies.append(cik)
                findings.append(
                    f"{data.name(cik)} revenue {label}: {a} to {b} ({100 * (b / a - 1):+.0f}%)"
                )
    return _check(
        "unrealistic_jumps",
        "Unrealistic quarter-to-quarter jumps",
        CheckStatus.WARNING if findings else CheckStatus.PASS,
        f"revenue changing by more than {int(JUMP * 100)}% from one quarter to the next",
        {"jumps": len(findings)},
        findings,
        companies,
    )


def cumulative_cashflow(data: AuditData) -> GateCheck:
    findings: list[str] = []
    checked = 0
    q4_equals_year = 0
    for metric in ("cfo", "capex"):
        for cik, rows in _quarterly(data, metric).items():
            years = {y for y, _ in rows}
            for year in years:
                parts = [rows.get((year, p)) for p in (*QUARTERS, FiscalPeriod.FY)]
                if any(p is None or p.value is None for p in parts):
                    continue
                values = [Decimal(p.value or "0") for p in parts if p is not None]
                total, annual = sum(values[:4], Decimal(0)), values[4]
                checked += 1
                if values[3] == annual and annual != 0:
                    q4_equals_year += 1
                    findings.append(f"{data.name(cik)} {metric} FY{year}: Q4 equals the year")
                flagged = any(QualityFlag.MIXED_VINTAGE in p.flags for p in parts if p is not None)
                if abs(total - annual) > SUM_TOLERANCE * abs(annual) and not flagged:
                    findings.append(
                        f"{data.name(cik)} {metric} FY{year}: quarters {total}, year {annual}"
                    )
    status = (
        CheckStatus.FAIL
        if q4_equals_year
        else CheckStatus.WARNING
        if findings
        else CheckStatus.PASS
    )
    return _check(
        "cumulative_cashflow",
        "Cumulative cash flow",
        status,
        "cash flow is reported year to date; the four quarters must add up to the year and Q4 "
        "is never the annual total",
        {
            "company-years checked": checked,
            "Q4 equal to the year": q4_equals_year,
            "sums off": len(findings) - q4_equals_year,
        },
        findings,
    )


def capex_identification(data: AuditData) -> GateCheck:
    concepts: Counter[str] = Counter()
    findings: list[str] = []
    companies: list[str] = []
    for cik, rows in data.current.items():
        for r in rows:
            if r.metric == "capex" and r.fiscal_period is FiscalPeriod.FY and r.concept:
                concepts[r.concept.split(":")[1]] += 1
                if QualityFlag.BROADER_CONCEPT in r.flags:
                    companies.append(cik)
                    findings.append(
                        f"{data.name(cik)} FY{r.fiscal_year}: {r.concept.split(':')[1]} (broader)"
                    )
    return _check(
        "capex_identification",
        "Misidentified CAPEX",
        CheckStatus.WARNING if findings else CheckStatus.PASS,
        "capex is PaymentsToAcquirePropertyPlantAndEquipment; a broader concept (productive "
        "assets, which can include intangibles) is used only when the primary one is absent, "
        "with a flag",
        {"concepts used (fiscal years)": ", ".join(f"{c} {n}" for c, n in concepts.most_common())},
        findings,
        companies,
    )


def ebitda(data: AuditData) -> GateCheck:
    narrower = sum(
        r.metric == "ebitda" and QualityFlag.NARROWER_CONCEPT in r.flags
        for rows in data.current.values()
        for r in rows
    )
    below = [
        f"{data.name(cik)} FY{r.fiscal_year} {r.fiscal_period.value}"
        for cik, rows in data.current.items()
        for r in rows
        if r.metric == "depreciation_amortization" and r.value is not None and Decimal(r.value) < 0
    ]
    return _check(
        "ebitda_reported_vs_calculated",
        "Reported vs calculated EBITDA",
        CheckStatus.WARNING,
        "EBITDA is not a US GAAP concept: filings tag no reported EBITDA to compare with. "
        "Calculated EBITDA = operating income + D&A, never adjusted; where D&A is the narrower "
        "depreciation line, EBITDA is flagged",
        {"EBITDA values with narrower D&A": narrower, "negative D&A": len(below)},
        below,
    )


def source_conflicts(data: AuditData) -> GateCheck:
    flags: Counter[str] = Counter()
    for rows in data.current.values():
        for r in rows:
            for flag in r.flags:
                if flag in (
                    QualityFlag.CONCEPT_DISAGREEMENT,
                    QualityFlag.CONFLICT_IN_FILING,
                    QualityFlag.SCALE_MISMATCH,
                    QualityFlag.MIXED_VINTAGE,
                ):
                    flags[flag.value] += 1
    alerts = Counter(
        f"{a.kind.value}" for a in data.alerts if a.severity is not QualitySeverity.INFO
    )
    blocking = sum(1 for a in data.alerts if a.severity is QualitySeverity.BLOCKING)
    return _check(
        "source_conflicts",
        "Source conflicts",
        CheckStatus.FAIL
        if blocking
        else CheckStatus.WARNING
        if flags or alerts
        else CheckStatus.PASS,
        "disagreements inside and between filings, as flags on values and chronology alerts",
        {
            **{k: v for k, v in flags.items()},
            **{f"alert {k}": v for k, v in alerts.items()},
            "blocking alerts": blocking,
        },
    )


CHECKS: tuple[Callable[[AuditData], GateCheck], ...] = (
    future_revisions,
    duplicated_company_quarters,
    concept_drift,
    survivorship,
    bankruptcies,
    missingness,
    revenue_gaps,
    ratios,
    currency,
    outliers,
    jumps,
    cumulative_cashflow,
    capex_identification,
    ebitda,
    source_conflicts,
)
