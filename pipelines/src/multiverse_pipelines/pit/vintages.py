"""Knowledge-time history of one company's normalized values (Stage 12, ADR-0019).

The Stage 11 normalizer runs once for every moment a filing of the company became
public, on exactly the facts public at that moment. Comparing consecutive runs gives,
for every metric, fiscal period and revision, the intervals during which each answer was
the current one. An as-of query therefore returns, by construction, what normalizing
the filings public at the cutoff would return: the fiscal calendar, the concept chosen
for a year, the reporting currency and every derived quarter come only from them. Rows
of periods that have not ended yet are kept too; a query shows only ended periods.

Facts that end after the filing that reported them are estimates (future amortization,
expected contributions), not values; they never enter a run, and a metric fact of that
kind raises a blocking alert.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.normalized import FiscalPeriod, NormalizedValue, Revision
from multiverse_contracts.pit import (
    AlertKind,
    ChronologyAlert,
    PitValue,
    SourceTiming,
    TimePrecision,
    ValueChange,
)
from multiverse_pipelines.pit.filings import FilingIndex
from multiverse_pipelines.sec.cik import cik10
from multiverse_pipelines.xbrl.concepts import METRICS
from multiverse_pipelines.xbrl.facts import Fact
from multiverse_pipelines.xbrl.normalize import CompanyNormalizer

METRIC_CONCEPTS = frozenset(c.concept for spec in METRICS for c in spec.candidates)
ValueKey = tuple[str, int, FiscalPeriod, Revision]


@dataclass
class CompanyHistory:
    cik: str
    values: list[PitValue] = field(default_factory=list)
    knowledge_points: int = 0
    estimates_dropped: int = 0
    alerts: list[ChronologyAlert] = field(default_factory=list)


def classify(before: NormalizedValue | None, after: NormalizedValue) -> ValueChange:
    if before is None:
        return ValueChange.FIRST_KNOWN
    if before.value is None:
        return ValueChange.VALUE_FILLED if after.value is not None else ValueChange.REQUALIFIED
    if after.value is None:
        return ValueChange.VALUE_WITHDRAWN
    if Decimal(before.value) != Decimal(after.value):
        return ValueChange.VALUE_REVISED
    if before.sources != after.sources:
        return ValueChange.CONFIRMED
    return ValueChange.REQUALIFIED


def _key(row: NormalizedValue) -> ValueKey:
    return (row.metric, row.fiscal_year, row.fiscal_period, row.revision)


def _closed(value: PitValue, at: datetime) -> PitValue:
    return PitValue.model_validate({**value.model_dump(), "known_to": at})


def fact_alerts(
    cik: str, facts: Sequence[Fact], index: FilingIndex
) -> tuple[list[ChronologyAlert], int]:
    """Alerts about the facts themselves, and how many estimates were found."""
    alerts: list[ChronologyAlert] = []
    estimates = 0
    seen: set[tuple[AlertKind, str]] = set()
    for fact in sorted(facts, key=lambda f: (f.filed, f.accession, f.concept, f.end)):
        filing = index.get(fact.accession)
        if fact.end > fact.filed:
            estimates += 1
            if fact.concept in METRIC_CONCEPTS:
                alerts.append(
                    ChronologyAlert(
                        kind=AlertKind.PERIOD_AFTER_FILING,
                        severity=QualitySeverity.BLOCKING,
                        cik=cik,
                        accession=fact.accession,
                        concept=fact.concept,
                        period_end=fact.end,
                        detail=(
                            f"{fact.concept} for a period ending {fact.end} was filed on "
                            f"{fact.filed}: an estimate, left out of every view"
                        ),
                    )
                )
        if filing is None and (AlertKind.MISSING_ACCEPTANCE, fact.accession) not in seen:
            seen.add((AlertKind.MISSING_ACCEPTANCE, fact.accession))
            alerts.append(
                ChronologyAlert(
                    kind=AlertKind.MISSING_ACCEPTANCE,
                    severity=QualitySeverity.WARNING,
                    cik=cik,
                    accession=fact.accession,
                    detail=(
                        f"{fact.accession} ({fact.form}) is not in the archived filing index: "
                        f"public from the end of its filing date {fact.filed}"
                    ),
                )
            )
        if filing is None or filing.filing_date == fact.filed:
            continue
        if (AlertKind.FILING_DATE_MISMATCH, fact.accession) not in seen:
            seen.add((AlertKind.FILING_DATE_MISMATCH, fact.accession))
            alerts.append(
                ChronologyAlert(
                    kind=AlertKind.FILING_DATE_MISMATCH,
                    severity=QualitySeverity.WARNING,
                    cik=cik,
                    accession=fact.accession,
                    known_at=filing.known_at,
                    detail=(
                        f"Company Facts says filed {fact.filed}, the filing index "
                        f"{filing.filing_date}; the index time is used"
                    ),
                )
            )
    return alerts, estimates


def build_history(cik: str, facts: Sequence[Fact], index: FilingIndex) -> CompanyHistory:
    cik = cik10(cik)
    history = CompanyHistory(cik)
    history.alerts, history.estimates_dropped = fact_alerts(cik, facts, index)
    timings: dict[str, SourceTiming] = {}
    for fact in facts:
        if fact.accession not in timings:
            timings[fact.accession] = index.timing(fact.accession, fact.filed)
    usable = sorted(
        (f for f in facts if f.end <= f.filed),
        key=lambda f: timings[f.accession].known_at,
    )
    points = sorted({timings[f.accession].known_at for f in usable})
    history.knowledge_points = len(points)
    current: dict[ValueKey, PitValue] = {}
    closed: list[PitValue] = []
    visible: list[Fact] = []
    position = 0
    for point in points:
        while position < len(usable) and timings[usable[position].accession].known_at <= point:
            visible.append(usable[position])
            position += 1
        rows = CompanyNormalizer(cik, visible, provisional=True).normalize()
        now = {_key(row): row for row in rows}
        for key, row in now.items():
            before = current.get(key)
            if before is not None and before.value == row:
                continue
            if before is not None:
                closed.append(_closed(before, point))
            accessions = sorted({source.accession for source in row.sources})
            current[key] = PitValue(
                value=row,
                known_from=point,
                change=classify(before.value if before else None, row),
                timings=tuple(timings[a] for a in accessions),
            )
        for key in [k for k in current if k not in now]:
            closed.append(_closed(current.pop(key), point))
    values = closed + list(current.values())
    history.values = sorted(values, key=lambda v: (_key(v.value), v.known_from))
    return history


def precision_counts(history: CompanyHistory) -> dict[TimePrecision, int]:
    counts: dict[TimePrecision, int] = defaultdict(int)
    for timing in {t for v in history.values for t in v.timings}:
        counts[timing.precision] += 1
    return dict(counts)
