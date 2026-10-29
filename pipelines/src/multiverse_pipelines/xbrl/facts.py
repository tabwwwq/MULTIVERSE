"""XBRL facts from a Company Facts file, grouped by what they measure.

Company Facts lists every fact once per filing that reported it: a 10-K repeats the prior
years as comparatives, a 10-K/A repeats the 10-K. Facts that measure the same concept,
unit and period form one observation, which knows the first filed fact (the original)
and the last one (the latest). It holds only facts without dimensions, that is values
of the consolidated entity: segment members cannot leak in from this file.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

FactKey = tuple[str, str, date | None, date]


@dataclass(frozen=True)
class Fact:
    concept: str
    unit: str
    start: date | None
    end: date
    value: Decimal
    accession: str
    form: str
    filed: date
    fy: int | None = None
    fp: str | None = None

    @property
    def key(self) -> FactKey:
        return (self.concept, self.unit, self.start, self.end)

    @property
    def length(self) -> int | None:
        """Days covered, both ends included; ``None`` for an instant."""
        return None if self.start is None else (self.end - self.start).days + 1

    @property
    def amended(self) -> bool:
        return self.form.endswith("/A")


@dataclass(frozen=True)
class Observation:
    """One concept, unit and period across every filing that reported it."""

    original: Fact
    latest: Fact
    filings: int
    conflicts: frozenset[str]


def facts_from_companyfacts(doc: Mapping[str, Any]) -> list[Fact]:
    facts: list[Fact] = []
    for taxonomy, concepts in doc["facts"].items():
        for tag, body in concepts.items():
            for unit, values in body["units"].items():
                for value in values:
                    start = value.get("start")
                    facts.append(
                        Fact(
                            concept=f"{taxonomy}:{tag}",
                            unit=unit,
                            start=date.fromisoformat(start) if start else None,
                            end=date.fromisoformat(value["end"]),
                            value=Decimal(str(value["val"])),
                            accession=value["accn"],
                            form=value["form"],
                            filed=date.fromisoformat(value["filed"]),
                            fy=value.get("fy"),
                            fp=value.get("fp"),
                        )
                    )
    return facts


def _filing_order(fact: Fact) -> tuple[date, bool, str]:
    # Same day: the original form before its amendment, then by accession number.
    return (fact.filed, fact.amended, fact.accession)


def observe(facts: Iterable[Fact]) -> tuple[dict[FactKey, Observation], int]:
    """Group facts; return the observations and how many exact duplicates were dropped."""
    groups: dict[FactKey, list[Fact]] = defaultdict(list)
    for fact in facts:
        groups[fact.key].append(fact)
    observations: dict[FactKey, Observation] = {}
    dropped = 0
    for key, items in groups.items():
        values: dict[str, set[Decimal]] = defaultdict(set)
        unique: dict[tuple[str, Decimal], Fact] = {}
        for fact in items:
            values[fact.accession].add(fact.value)
            unique.setdefault((fact.accession, fact.value), fact)
        dropped += len(items) - len(unique)
        ordered = sorted(unique.values(), key=_filing_order)
        observations[key] = Observation(
            original=ordered[0],
            latest=ordered[-1],
            filings=len({fact.accession for fact in ordered}),
            conflicts=frozenset(a for a, found in values.items() if len(found) > 1),
        )
    return observations, dropped
