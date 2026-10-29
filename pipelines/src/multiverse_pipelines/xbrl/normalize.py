"""Canonical values of one company from its XBRL facts (Stage 11, ADR-0018).

For each metric, fiscal year, fiscal period and revision there is exactly one row: a
value with its source facts, or a missing reason. Quarters come from what the filings
report, in this order:

- the quarter itself, when a filing reports the three months;
- year-to-date differences of one concept: Q2 = H1 - Q1, Q3 = 9M - H1;
- Q4 = FY - 9M, or FY - Q1 - Q2 - Q3 when all three quarters are reported. Q4 is a
  derived quarter, never the annual total; the annual total is the FY row.

Averages (weighted shares) are never subtracted, and instant values (cash, debt, shares
outstanding) are taken at quarter ends as reported, never derived. A derivation never
mixes concepts. ``original`` uses each fact as first filed, ``latest`` as last filed.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.metrics import LineageMethod
from multiverse_contracts.normalized import (
    DERIVED_METHODS,
    ConceptCheck,
    ConceptRelation,
    FiscalPeriod,
    NormalizedValue,
    PeriodKind,
    QualityFlag,
    Revision,
    SourceFact,
)
from multiverse_pipelines.sec.cik import cik10
from multiverse_pipelines.xbrl.calendar import FiscalCalendar, FiscalYear
from multiverse_pipelines.xbrl.concepts import (
    CALCULATED,
    METRICS,
    CalculatedSpec,
    Candidate,
    MetricSpec,
)
from multiverse_pipelines.xbrl.facts import Fact, Observation, observe

DURATION_PERIODS = tuple(FiscalPeriod)
INSTANT_PERIODS = (FiscalPeriod.Q1, FiscalPeriod.Q2, FiscalPeriod.Q3, FiscalPeriod.Q4)
# Equivalent concepts may round differently; a larger gap means they measure different things.
DISAGREEMENT_SHARE = Decimal("0.005")
LONG_QUARTER_DAYS = 96
SCALE_RATIOS = (Decimal(1000), Decimal(1_000_000))
SCALE_TOLERANCE = Decimal("0.01")
SAME_MEANING = frozenset({ConceptRelation.PRIMARY, ConceptRelation.EQUIVALENT})
RELATION_FLAGS = {
    ConceptRelation.BROADER: QualityFlag.BROADER_CONCEPT,
    ConceptRelation.NARROWER: QualityFlag.NARROWER_CONCEPT,
}
Plan = tuple[LineageMethod, tuple[tuple[str, int], ...]]
PeriodKey = tuple[str, str, int, FiscalPeriod]


@dataclass(frozen=True)
class Computed:
    value: Decimal
    method: LineageMethod
    parts: tuple[tuple[Fact, int], ...]


@dataclass(frozen=True)
class Blocked:
    reason: str


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return "0" if text in ("-0", "") else text


def rounding(value: Decimal) -> int:
    """The power of ten a reported value is rounded to, up to millions."""
    if value == 0:
        return 0
    power = 0
    while power < 6 and value % (Decimal(10) ** (power + 1)) == 0:
        power += 1
    return power


def reporting_currency(facts: Iterable[Fact]) -> str:
    counts = Counter(
        f.unit
        for f in facts
        if f.concept.startswith("us-gaap:") and len(f.unit) == 3 and f.unit.isupper()
    )
    return counts.most_common(1)[0][0] if counts else "USD"


def _plans(spec: MetricSpec, period: FiscalPeriod) -> tuple[Plan, ...]:
    reported = LineageMethod.REPORTED
    if spec.kind is PeriodKind.INSTANT:
        return ((reported, ((f"I{period.value[1]}", 1),)),)
    if period is FiscalPeriod.FY:
        return ((reported, (("FY", 1),)),)
    own: Plan = (reported, ((period.value, 1),))
    if not spec.additive or period is FiscalPeriod.Q1:
        return (own,)
    if period is FiscalPeriod.Q2:
        return (own, (LineageMethod.YTD_TO_QUARTER, (("H1", 1), ("Q1", -1))))
    if period is FiscalPeriod.Q3:
        return (own, (LineageMethod.YTD_TO_QUARTER, (("9M", 1), ("H1", -1))))
    return (
        own,
        (LineageMethod.FY_MINUS_NINE_MONTHS, (("FY", 1), ("9M", -1))),
        (LineageMethod.FY_MINUS_THREE_QUARTERS, (("FY", 1), ("Q1", -1), ("Q2", -1), ("Q3", -1))),
    )


def _missing_reason(spec: MetricSpec, period: FiscalPeriod) -> str:
    if not spec.additive and period in (FiscalPeriod.Q2, FiscalPeriod.Q3, FiscalPeriod.Q4):
        return f"{spec.label} is an average, not a sum: only a reported quarter is used"
    if spec.kind is PeriodKind.DURATION and period is FiscalPeriod.Q4:
        return "Q4 needs the fiscal year and the first nine months, or three reported quarters"
    if spec.kind is PeriodKind.DURATION and period in (FiscalPeriod.Q2, FiscalPeriod.Q3):
        return f"No {period.value} reported and no year-to-date pair of one concept to derive it"
    return f"No candidate concept for {spec.label.lower()} reported for this period"


class CompanyNormalizer:
    def __init__(self, cik: str, facts: Sequence[Fact]) -> None:
        self.cik = cik10(cik)
        self.calendar = FiscalCalendar.from_facts(facts)
        self.currency = reporting_currency(facts)
        observations, self.duplicates = observe(facts)
        self.ambiguous = 0
        self.unplaced = 0
        self._index: dict[tuple[str, str], dict[tuple[int, str], Observation]] = defaultdict(dict)
        for (concept, unit, start, end), observation in observations.items():
            placed = self.calendar.slot(start, end)
            if placed is None:
                self.unplaced += 1
                continue
            year, slot = placed
            target = self._index[(concept, unit)]
            known = target.get((year.label, slot))
            if known is not None:
                self.ambiguous += 1
                if known.filings >= observation.filings:
                    continue
            target[(year.label, slot)] = observation

    def _unit(self, spec: MetricSpec) -> str:
        return self.currency if spec.unit == "money" else "shares"

    def _fact(
        self, concept: str, unit: str, year: FiscalYear, slot: str, revision: Revision
    ) -> Fact | Blocked | None:
        observation = self._index.get((concept, unit), {}).get((year.label, slot))
        if observation is None:
            return None
        fact = observation.original if revision is Revision.ORIGINAL else observation.latest
        if fact.accession in observation.conflicts:
            return Blocked(f"{concept} has conflicting values in filing {fact.accession}")
        return fact

    def compute(
        self,
        spec: MetricSpec,
        concept: str,
        year: FiscalYear,
        period: FiscalPeriod,
        revision: Revision,
    ) -> Computed | Blocked | None:
        unit = self._unit(spec)
        for method, slots in _plans(spec, period):
            found = [self._fact(concept, unit, year, slot, revision) for slot, _ in slots]
            blocked = next((f for f in found if isinstance(f, Blocked)), None)
            if blocked is not None:
                return blocked
            facts = [f for f in found if isinstance(f, Fact)]
            if len(facts) == len(slots):
                parts = tuple((fact, sign) for fact, (_, sign) in zip(facts, slots, strict=True))
                value = sum((fact.value * sign for fact, sign in parts), Decimal(0))
                return Computed(value, method, parts)
        return None

    def _year_concept(
        self, spec: MetricSpec, year: FiscalYear, revision: Revision
    ) -> Candidate | None:
        anchor = "I4" if spec.kind is PeriodKind.INSTANT else "FY"
        unit = self._unit(spec)
        for candidate in spec.candidates:
            if isinstance(self._fact(candidate.concept, unit, year, anchor, revision), Fact):
                return candidate
        for candidate in spec.candidates:
            slots = self._index.get((candidate.concept, unit), {})
            if any(label == year.label for label, _ in slots):
                return candidate
        return None

    @staticmethod
    def _dates(
        spec: MetricSpec, year: FiscalYear, period: FiscalPeriod
    ) -> tuple[date | None, date]:
        if spec.kind is PeriodKind.INSTANT:
            return None, year.quarter_ends[int(period.value[1]) - 1]
        if period is FiscalPeriod.FY:
            return year.start, year.end
        return year.quarter(int(period.value[1]))

    def row(
        self, spec: MetricSpec, year: FiscalYear, period: FiscalPeriod, revision: Revision
    ) -> NormalizedValue:
        start, end = self._dates(spec, year, period)
        base: dict[str, object] = {
            "cik": self.cik,
            "metric": spec.metric,
            "fiscal_year": year.label,
            "fiscal_period": period,
            "period_kind": spec.kind,
            "revision": revision,
            "unit": self._unit(spec),
            "currency": self.currency if spec.unit == "money" else None,
            "period_start": start,
            "period_end": end,
        }
        chosen = self._year_concept(spec, year, revision)
        order = ([chosen] if chosen else []) + [c for c in spec.candidates if c != chosen]
        for position, candidate in enumerate(order):
            result = self.compute(spec, candidate.concept, year, period, revision)
            if isinstance(result, Blocked):
                if position == 0:
                    return NormalizedValue.model_validate(
                        {
                            **base,
                            "value": None,
                            "missing_reason": result.reason,
                            "quality": QualitySeverity.BLOCKING,
                            "flags": (QualityFlag.CONFLICT_IN_FILING,),
                        }
                    )
                continue
            if result is not None:
                return self._value_row(
                    spec, year, period, revision, base, candidate, chosen, result
                )
        return NormalizedValue.model_validate(
            {
                **base,
                "value": None,
                "missing_reason": _missing_reason(spec, period),
                "quality": QualitySeverity.INFO,
            }
        )

    def _value_row(
        self,
        spec: MetricSpec,
        year: FiscalYear,
        period: FiscalPeriod,
        revision: Revision,
        base: dict[str, object],
        candidate: Candidate,
        chosen: Candidate | None,
        result: Computed,
    ) -> NormalizedValue:
        flags: set[QualityFlag] = set()
        if candidate != chosen:
            flags.add(QualityFlag.CONCEPT_FALLBACK)
        if candidate.relation in RELATION_FLAGS:
            flags.add(RELATION_FLAGS[candidate.relation])
        if candidate.flag is not None:
            flags.add(candidate.flag)
        if any(fact.amended for fact, _ in result.parts):
            flags.add(QualityFlag.FROM_AMENDMENT)
        if spec.positive and result.value < 0:
            derived = result.method in DERIVED_METHODS
            flags.add(QualityFlag.NEGATIVE_DERIVED if derived else QualityFlag.NEGATIVE_EXPENSE)
        if spec.unit == "money" and self.currency != "USD":
            flags.add(QualityFlag.NON_USD)
        start, end = self._dates(spec, year, period)
        if start is not None and year.fifty_three_weeks:
            long_quarter = (end - start).days + 1 >= LONG_QUARTER_DAYS
            if period is FiscalPeriod.FY or long_quarter:
                flags.add(QualityFlag.FIFTY_THREE_WEEKS)
        if result.method in DERIVED_METHODS:
            powers = [rounding(fact.value) for fact, _ in result.parts if fact.value != 0]
            if powers and max(powers) - min(powers) >= 3:
                flags.add(QualityFlag.MIXED_ROUNDING)

        alternatives: list[ConceptCheck] = []
        for other in spec.candidates:
            if other == candidate:
                continue
            found = self.compute(spec, other.concept, year, period, revision)
            if not isinstance(found, Computed):
                continue
            difference = result.value - found.value
            alternatives.append(
                ConceptCheck(
                    concept=other.concept,
                    relation=other.relation,
                    value=decimal_text(found.value),
                    difference=decimal_text(difference),
                )
            )
            same = candidate.relation in SAME_MEANING and other.relation in SAME_MEANING
            if same and abs(difference) > DISAGREEMENT_SHARE * abs(result.value):
                flags.add(QualityFlag.CONCEPT_DISAGREEMENT)

        latest = max(fact.filed for fact, _ in result.parts)
        accession = max(fact.accession for fact, _ in result.parts if fact.filed == latest)
        return NormalizedValue.model_validate(
            {
                **base,
                "value": decimal_text(result.value),
                "concept": candidate.concept,
                "method": result.method,
                "accession": accession,
                "filed": latest,
                "sources": tuple(_source(fact, sign) for fact, sign in result.parts),
                "alternatives": tuple(alternatives),
                "quality": QualitySeverity.WARNING if flags else QualitySeverity.INFO,
                "flags": tuple(flag for flag in QualityFlag if flag in flags),
            }
        )

    def normalize(self) -> list[NormalizedValue]:
        rows = [
            self.row(spec, year, period, revision)
            for spec in METRICS
            for year in self.calendar.years
            for revision in Revision
            for period in (INSTANT_PERIODS if spec.kind is PeriodKind.INSTANT else DURATION_PERIODS)
        ]
        rows += calculated_rows(rows, CALCULATED)
        return mark_restatements(rows)


def _source(fact: Fact, sign: int) -> SourceFact:
    return SourceFact(
        concept=fact.concept,
        unit=fact.unit,
        period_start=fact.start,
        period_end=fact.end,
        value=decimal_text(fact.value),
        accession=fact.accession,
        form=fact.form,
        filed=fact.filed,
        sign=1 if sign > 0 else -1,
    )


def calculated_rows(
    rows: Sequence[NormalizedValue], specs: Sequence[CalculatedSpec]
) -> list[NormalizedValue]:
    """Values computed from canonical values of the same period and revision."""
    index = {(r.metric, r.fiscal_year, r.fiscal_period, r.revision): r for r in rows}
    periods = sorted(
        {
            (r.fiscal_year, r.fiscal_period, r.revision)
            for r in rows
            if r.period_kind is PeriodKind.DURATION
        }
    )
    made: list[NormalizedValue] = []
    for spec in specs:
        names = spec.plus + spec.minus
        for year, period, revision in periods:
            parts = [index.get((name, year, period, revision)) for name in names]
            if any(part is None for part in parts):
                continue
            present = [part for part in parts if part is not None]
            first = present[0]
            base: dict[str, object] = {
                "cik": first.cik,
                "metric": spec.metric,
                "fiscal_year": year,
                "fiscal_period": period,
                "period_kind": PeriodKind.DURATION,
                "period_start": first.period_start,
                "period_end": first.period_end,
                "revision": revision,
                "unit": first.unit,
                "currency": first.currency,
                "formula": spec.formula,
            }
            missing = [p.metric for p in present if p.value is None]
            if missing or len({p.currency for p in present}) != 1:
                reason = (
                    f"{spec.formula}: missing {', '.join(missing)}"
                    if missing
                    else f"{spec.formula}: components in different currencies"
                )
                made.append(
                    NormalizedValue.model_validate(
                        {
                            **base,
                            "value": None,
                            "missing_reason": reason,
                            "quality": QualitySeverity.INFO,
                        }
                    )
                )
                continue
            signs = [1] * len(spec.plus) + [-1] * len(spec.minus)
            value = sum(
                (Decimal(p.value or "0") * s for p, s in zip(present, signs, strict=True)),
                Decimal(0),
            )
            sources = tuple(
                source.model_copy(update={"sign": source.sign * s})
                for p, s in zip(present, signs, strict=True)
                for source in p.sources
            )
            flags = {flag for p in present for flag in p.flags if flag is not QualityFlag.RESTATED}
            latest = max(source.filed for source in sources)
            made.append(
                NormalizedValue.model_validate(
                    {
                        **base,
                        "value": decimal_text(value),
                        "method": LineageMethod.CALCULATED,
                        "accession": max(s.accession for s in sources if s.filed == latest),
                        "filed": latest,
                        "sources": sources,
                        "quality": QualitySeverity.WARNING if flags else QualitySeverity.INFO,
                        "flags": tuple(flag for flag in QualityFlag if flag in flags),
                    }
                )
            )
    return made


def scale_mismatch(a: str, b: str) -> bool:
    """A thousand or a million times apart (within rounding): a value filed without its scale."""
    x, y = abs(Decimal(a)), abs(Decimal(b))
    if x == 0 or y == 0:
        return False
    ratio = max(x, y) / min(x, y)
    return any(abs(ratio / scale - 1) <= SCALE_TOLERANCE for scale in SCALE_RATIOS)


def _with_flags(row: NormalizedValue, added: set[QualityFlag], **update: object) -> NormalizedValue:
    flags = {*row.flags, *added}
    return NormalizedValue.model_validate(
        {
            **row.model_dump(),
            **update,
            "quality": QualitySeverity.WARNING,
            "flags": tuple(flag for flag in QualityFlag if flag in flags),
        }
    )


def mark_restatements(rows: Sequence[NormalizedValue]) -> list[NormalizedValue]:
    """A latest value that differs from the original one is a restatement: keep both.

    When the two differ exactly by a thousand or a million, one of them was filed without
    its scale (Company Facts has no ``decimals``); both rows are flagged.
    """
    pairs: dict[PeriodKey, dict[Revision, NormalizedValue]] = defaultdict(dict)
    for row in rows:
        pairs[(row.cik, row.metric, row.fiscal_year, row.fiscal_period)][row.revision] = row
    restated: dict[PeriodKey, str] = {}
    scaled: set[PeriodKey] = set()
    for key, pair in pairs.items():
        first, last = pair.get(Revision.ORIGINAL), pair.get(Revision.LATEST)
        if first is None or last is None or first.value is None or last.value is None:
            continue
        if Decimal(first.value) != Decimal(last.value):
            restated[key] = first.value
            if scale_mismatch(first.value, last.value):
                scaled.add(key)
    marked: list[NormalizedValue] = []
    for row in rows:
        key = (row.cik, row.metric, row.fiscal_year, row.fiscal_period)
        added = {QualityFlag.SCALE_MISMATCH} if key in scaled else set()
        if row.revision is Revision.LATEST and key in restated:
            row = _with_flags(row, {*added, QualityFlag.RESTATED}, original_value=restated[key])
        elif added:
            row = _with_flags(row, added)
        marked.append(row)
    return marked
