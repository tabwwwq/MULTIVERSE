"""The label quality of the registry, measured: what causal work may stand on (docs/05).

Windows come from the first public document of an event: what was filed and when, never
what a later dataset shows. Two events of a firm overlap when their windows meet.
"""

from collections import Counter
from datetime import datetime, timedelta

from multiverse_contracts.events import (
    CandidateSample,
    CorporateEvent,
    CountRow,
    EventRegistry,
    EventType,
    OverlapCell,
    QualityAudit,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.events.candidates import Filing
from multiverse_pipelines.pit.clock import eastern_date

WINDOW_DAYS = 365
MIN_EVENTS_PER_TYPE = 30
MIN_HUMAN_SHARE = 0.5
MIN_AGREEMENT = 0.8
FIELDS = ("announced_at", "effective_on", "reporting_lag_days", "magnitude", "funding")
INDEX_ITEMS = ("2.01", "2.03", "2.05")


def anchor(event: CorporateEvent) -> datetime:
    """The start of the event window: the first document that made it public."""
    return min(e.filed_at for e in event.evidence)


def window(event: CorporateEvent, days: int = WINDOW_DAYS) -> tuple[datetime, datetime]:
    moment = anchor(event)
    return moment - timedelta(days=days), moment + timedelta(days=days)


def overlaps(events: tuple[CorporateEvent, ...], days: int) -> list[OverlapCell]:
    counts: Counter[tuple[EventType, EventType]] = Counter()
    for i, first in enumerate(events):
        for second in events[i + 1 :]:
            close = abs(anchor(first) - anchor(second)) <= timedelta(days=days)
            if first.cik == second.cik and close:
                pair = sorted((first.event_type, second.event_type), key=lambda t: t.value)
                counts[(pair[0], pair[1])] += 1
    return [OverlapCell(first=a, second=b, pairs=n) for (a, b), n in sorted(counts.items())]


def index_overlap(
    events: tuple[CorporateEvent, ...], filings: dict[str, list[Filing]], days: int
) -> tuple[CountRow, ...]:
    """Events with another 8-K of a decision item in their window: unread pointers, a floor
    under the overlap that the small sample itself cannot show."""
    counts: Counter[str] = Counter()
    for event in events:
        moment = eastern_date(anchor(event))
        own = {e.accession for e in event.evidence}
        near = {
            item
            for filing in filings.get(event.cik, [])
            if filing.form == "8-K"
            and filing.accession not in own
            and abs((filing.filed_on - moment).days) <= days
            for item in filing.items
            if item in INDEX_ITEMS
        }
        for item in near:
            counts[f"{event.event_type.value} near item {item}"] += 1
    return count_rows(counts)


def count_rows(counter: Counter[str]) -> tuple[CountRow, ...]:
    return tuple(CountRow(key=k, count=v) for k, v in sorted(counter.items()))


def missing_fields(event: CorporateEvent) -> set[str]:
    found = set(event.unknown_fields)
    if event.announced_at is None:
        found.add("announced_at")
    if event.effective_on is None:
        found.add("effective_on")
    if event.reporting_lag_days is None:
        found.add("reporting_lag_days")
    if event.magnitude.value is None:
        found.add("magnitude")
    funding = event.funding
    if all(s is None for s in (funding.cash, funding.debt, funding.equity, funding.other)):
        found.add("funding")
    return found


def audit(
    registry: EventRegistry,
    sample: CandidateSample,
    filings: dict[str, list[Filing]] | None = None,
) -> QualityAudit:
    if registry.sample_id != sample.sample_id:
        raise ValueError("the registry was read from another sample")
    events = registry.events
    human = [e for e in events if any(r.kind == "human" for r in e.reviews)]
    double = [e for e in events if len({r.reviewer for r in e.reviews}) >= 2]
    agreed = [e for e in double if len({r.decision for r in e.reviews}) == 1]
    agreement = len(agreed) / len(double) if double else None
    by_type = Counter(e.event_type.value for e in events)
    missing = Counter(field for e in events for field in missing_fields(e))
    blockers: list[str] = []
    for kind in EventType:
        if by_type[kind.value] < MIN_EVENTS_PER_TYPE:
            blockers.append(
                f"{kind.value}: {by_type[kind.value]} events, at least "
                f"{MIN_EVENTS_PER_TYPE} are needed"
            )
    if len(human) < MIN_HUMAN_SHARE * max(len(events), 1):
        blockers.append(f"{len(human)} of {len(events)} events have a human review")
    if agreement is None:
        blockers.append("no event has two reviewers")
    elif agreement < MIN_AGREEMENT:
        blockers.append(f"reviewers agree on {100 * agreement:.0f}% of double-reviewed events")
    return QualityAudit(
        registry_version=registry.registry_version,
        sample_id=registry.sample_id,
        candidates_read=len(events) + len(registry.rejected),
        events=len(events),
        rejected=len(registry.rejected),
        by_type=count_rows(by_type),
        by_completion=count_rows(Counter(e.completion.value for e in events)),
        by_division=count_rows(Counter(e.division for e in events)),
        deregistered_events=sum(e.deregistered for e in events),
        human_reviewed=len(human),
        double_reviewed=len(double),
        reviewer_agreement=agreement,
        unknown_rate=tuple(CountRow(key=f, count=missing[f]) for f in FIELDS),
        confounded=sum(bool(e.confounded_by) for e in events),
        overlap=tuple(overlaps(events, WINDOW_DAYS)),
        overlap_window_days=WINDOW_DAYS,
        index_overlap=index_overlap(events, filings or {}, WINDOW_DAYS),
        credible_for_causal_work=not blockers,
        blockers=tuple(blockers),
        contracts_version=CONTRACTS_VERSION,
    )


def markdown(report: QualityAudit) -> str:
    def table(title: str, rows: tuple[CountRow, ...]) -> list[str]:
        return [
            f"## {title}",
            "",
            "| Value | Events |",
            "|---|---|",
            *(f"| {r.key} | {r.count} |" for r in rows),
            "",
        ]

    verdict = "credible" if report.credible_for_causal_work else "not credible: causal work blocked"
    agreement = (
        "no double review"
        if report.reviewer_agreement is None
        else f"{100 * report.reviewer_agreement:.0f}%"
    )
    lines = [
        f"# Event registry quality, {report.registry_version}",
        "",
        f"Sample `{report.sample_id}`: {report.candidates_read} filings read, {report.events} "
        f"events, {report.rejected} rejected. Verdict: {verdict}.",
        "",
        f"Human reviews: {report.human_reviewed}. Two reviewers: {report.double_reviewed}. "
        f"Agreement: {agreement}. Deregistered companies: {report.deregistered_events}. "
        f"Confounded: {report.confounded}.",
        "",
        *table("By type", report.by_type),
        *table("By completion", report.by_completion),
        *table("By SIC division", report.by_division),
        *table("Unknown fields", report.unknown_rate),
        f"## Overlap within {report.overlap_window_days} days",
        "",
        "| First | Second | Pairs |",
        "|---|---|---|",
        *(f"| {c.first.value} | {c.second.value} | {c.pairs} |" for c in report.overlap),
        "",
        "## Unread 8-K filings of decision items in the same window",
        "",
        "| Event and item | Events |",
        "|---|---|",
        *(f"| {r.key} | {r.count} |" for r in report.index_overlap),
        "",
        "## Blockers",
        "",
        *(f"- {b}" for b in report.blockers),
        "",
    ]
    return "\n".join(lines)
