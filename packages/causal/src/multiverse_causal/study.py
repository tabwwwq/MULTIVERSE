"""The feasibility study: every treatment, every method, measured and judged by set rules."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from multiverse_causal.design import COMMON, ESTIMANDS, EXTRA, GRAPH, RULES, UNTESTED
from multiverse_causal.diagnostics import (
    Treated,
    excluded_mask,
    null_rows,
    placebo_dates,
    pre_trends,
    support_and_balance,
    synthetic_fit,
    usable_events,
)
from multiverse_causal.panel import OUTCOMES, Panel, quarter_of
from multiverse_contracts.causal import (
    CausalStudy,
    LeadRow,
    MethodVerdict,
    NullRow,
    PlaceboRow,
    TreatmentStudy,
)
from multiverse_contracts.events import (
    CandidateSample,
    CorporateEvent,
    EventRegistry,
    EventType,
    QualityAudit,
)
from multiverse_contracts.version import CONTRACTS_VERSION

MIN_EVENTS = 30
MIN_SUPPORT = 0.9
MAX_SMD = 0.25
MAX_PLACEBO_SHARE = 0.1
MAX_FALSE_POSITIVES = 0.1
MIN_SYNTHETIC_SHARE = 0.5
MAX_HOLDOUT_RATIO = 1.5
MARGIN_QUARTERS = 8
NEAR_QUARTERS = 4
ITEMS = {
    EventType.ACQUISITION: ("2.01",),
    EventType.DIVESTITURE: ("2.01",),
    EventType.LAYOFF: ("2.05",),
    EventType.REFINANCING: ("2.03",),
    EventType.RND_CHANGE: (),
    EventType.CAPEX_CHANGE: (),
}
POOLS = {
    EventType.ACQUISITION: "item_2_01",
    EventType.DIVESTITURE: "item_2_01",
    EventType.LAYOFF: "item_2_05",
    EventType.REFINANCING: "item_2_03",
    EventType.RND_CHANGE: "rnd_jump",
    EventType.CAPEX_CHANGE: "capex_jump",
}
Index = dict[str, list[tuple[date, str]]]


def read_index(path: Path) -> Index:
    """The decision items of the filing index, per company."""
    found: Index = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            found[row["cik"]].append((date.fromisoformat(row["filed_on"]), row["item"]))
    return found


def anchor_of(event: CorporateEvent) -> datetime:
    return min(e.filed_at for e in event.evidence)


def treated_of(panel: Panel, events: list[CorporateEvent]) -> list[Treated]:
    """The event quarter is the first quarter that ends after the first public document."""
    found: list[Treated] = []
    for event in events:
        firm = panel.index(event.cik)
        if firm is None:
            continue
        column = panel.column(quarter_of(anchor_of(event).date()))
        if 0 <= column < panel.quarters:
            found.append(Treated(firm, column))
    return found


def marks_of(panel: Panel, index: Index, items: tuple[str, ...]) -> dict[int, list[int]]:
    marks: dict[int, list[int]] = {}
    for cik, rows in index.items():
        firm = panel.index(cik)
        if firm is None:
            continue
        columns = [panel.column(quarter_of(day)) for day, item in rows if item in items]
        if columns:
            marks[firm] = columns
    return marks


def near_decision_share(events: list[CorporateEvent], index: Index) -> float:
    """Events with another decision filing within a year."""
    if not events:
        return 0.0
    days = NEAR_QUARTERS * 91
    near = 0
    for event in events:
        moment = anchor_of(event).date()
        rows = index.get(event.cik, [])
        if any(0 < abs((day - moment).days) <= days for day, _ in rows):
            near += 1
    return near / len(events)


def lead_failures(rows: tuple[LeadRow, ...]) -> dict[str, int]:
    failures: Counter[str] = Counter()
    for row in rows:
        if row.low > 0 or row.high < 0:
            failures[row.outcome] += 1
    return dict(failures)


def placebo_share(rows: tuple[PlaceboRow, ...]) -> float | None:
    if not rows:
        return None
    return sum(r.low > 0 or r.high < 0 for r in rows) / len(rows)


def worst_false_positives(rows: tuple[NullRow, ...]) -> float | None:
    return max((r.false_positive_rate for r in rows), default=None)


def verdicts(study: TreatmentStudy, audit: QualityAudit) -> tuple[MethodVerdict, ...]:
    """The rules of ``RULES``, applied: a method is feasible only if no reason stands."""
    common: list[str] = []
    if not audit.credible_for_causal_work:
        common.append("The registry audit says the sample is not credible.")
    sample: list[str] = []
    if study.usable < MIN_EVENTS:
        sample.append(f"{study.usable} usable events, {MIN_EVENTS} are needed.")
    support: list[str] = []
    if study.support is None or study.support < MIN_SUPPORT:
        shown = "unknown" if study.support is None else f"{100 * study.support:.0f}%"
        support.append(f"Support is {shown}, at least 90% is needed.")
    worst = max((abs(b.after) for b in study.balance), default=None)
    balance: list[str] = []
    if worst is None or worst > MAX_SMD:
        shown = "unknown" if worst is None else f"{worst:.2f}"
        balance.append(f"The largest difference after matching is {shown}, at most 0.25 allowed.")
    trends = [
        f"{count} leads of {outcome} are away from zero."
        for outcome, count in lead_failures(study.leads).items()
        if count > 1
    ]
    share = placebo_share(study.placebo)
    placebo = (
        [f"{100 * share:.0f}% of placebo dates are away from zero."]
        if share is not None and share > MAX_PLACEBO_SHARE
        else []
    )
    if share is None:
        placebo = ["No placebo date could be measured."]
    false = worst_false_positives(study.null)
    null = (
        [f"The null rejects {100 * false:.0f}% of the time at a nominal 5%."]
        if false is not None and false > MAX_FALSE_POSITIVES
        else []
    )
    fit = study.synthetic
    synthetic = list(common)
    if fit is None or fit.usable < MIN_SYNTHETIC_SHARE * max(study.usable, 1):
        synthetic.append("Too few events have enough quarters and donors.")
    if fit is not None and (
        fit.median_holdout_ratio is None or fit.median_holdout_ratio > MAX_HOLDOUT_RATIO
    ):
        synthetic.append("The fit does not hold on the last pre-quarters.")
    plans = {
        "matched_cohort": common + sample + support + balance,
        "weighted_regression": common + sample + support,
        "did_event_study": common + sample + trends + placebo + null,
        "synthetic_control": synthetic,
    }
    return tuple(
        MethodVerdict(method=method, feasible=not reasons, reasons=tuple(reasons))  # type: ignore[arg-type]
        for method, reasons in plans.items()
    )


def study_treatment(
    kind: EventType,
    registry: EventRegistry,
    sample: CandidateSample,
    audit: QualityAudit,
    panel: Panel,
    index: Index,
    seed: int,
) -> TreatmentStudy:
    events = [e for e in registry.events if e.event_type is kind]
    treated = treated_of(panel, events)
    usable = usable_events(panel, treated)
    excluded = excluded_mask(panel, marks_of(panel, index, ITEMS[kind]), MARGIN_QUARTERS, treated)
    pool = sample.population.get(POOLS[kind], 0)
    support, balance = support_and_balance(panel, usable, excluded)
    divisions = Counter(panel.divisions[e.firm] for e in usable)
    study = TreatmentStudy(
        treatment=kind,
        estimand=ESTIMANDS[kind],
        assumptions=(*COMMON, *EXTRA[kind]),
        untested=UNTESTED,
        events=len(events),
        usable=len(usable),
        candidate_pool=pool,
        controls=int((~excluded.all(axis=1)).sum()),
        support=support,
        balance=tuple(balance),
        leads=tuple(pre_trends(panel, usable, excluded)),
        placebo=tuple(placebo_dates(panel, usable, excluded)),
        null=tuple(null_rows(panel, excluded, len(usable), pool, seed)),
        synthetic=synthetic_fit(panel, usable, excluded),
        confounded_share=sum(bool(e.confounded_by) for e in events) / max(len(events), 1),
        near_decision_share=near_decision_share(events, index),
        divisions=dict(sorted(divisions.items())),
        verdicts=(MethodVerdict(method="matched_cohort", feasible=False, reasons=("pending",)),),
    )
    return study.model_copy(update={"verdicts": verdicts(study, audit)})


def findings_of(treatments: list[TreatmentStudy]) -> list[str]:
    lines: list[str] = [
        "No effect was estimated, and no outcome after a treatment was read.",
    ]
    for t in treatments:
        open_methods = [v.method for v in t.verdicts if v.feasible]
        growth = next((n for n in t.null if n.outcome == OUTCOMES[0]), None)
        minimum = (
            ""
            if growth is None
            else f"; smallest growth effect detectable now {growth.minimum_effect_now:.3f}"
        )
        lines.append(
            f"{t.treatment.value}: {t.usable} of {t.events} events usable, "
            f"{len(open_methods)} of {len(t.verdicts)} methods feasible{minimum}"
        )
    return lines


def run_study(
    registry: EventRegistry,
    sample: CandidateSample,
    audit: QualityAudit,
    panel: Panel,
    index: Index,
    dataset_id: str,
    data_cutoff: datetime,
    seed: int,
    day: date,
    progress: Callable[[str], None] = print,
) -> CausalStudy:
    treatments: list[TreatmentStudy] = []
    for kind in EventType:
        treatments.append(study_treatment(kind, registry, sample, audit, panel, index, seed))
        progress(f"{kind.value} done")
    payload = {
        "dataset": dataset_id,
        "registry": registry.registry_version,
        "sample": sample.sample_id,
        "seed": seed,
        "treatments": [t.model_dump(mode="json") for t in treatments],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode()).hexdigest()
    return CausalStudy(
        study_id=f"cst-{day:%Y%m%d}-{digest[:12]}",
        sha256=digest,
        label="feasibility_study_no_effect_estimated",
        effects_estimated=0,
        outcomes_after_treatment_read=False,
        data_cutoff=data_cutoff,
        dataset_id=dataset_id,
        registry_version=registry.registry_version,
        sample_id=sample.sample_id,
        audit_credible=audit.credible_for_causal_work,
        audit_blockers=audit.blockers,
        graph=GRAPH,
        rules=RULES,
        treatments=tuple(treatments),
        findings=tuple(findings_of(treatments)),
        seed=seed,
        contracts_version=CONTRACTS_VERSION,
        created_at=datetime.now(UTC),
    )
