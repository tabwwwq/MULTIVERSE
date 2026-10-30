"""Fiscal calendar of one company, read from its own facts.

Fiscal years are the one-year periods that 10-K filings report (350 to 380 days, so
52- and 53-week years both fit). A year is named by the ``fy`` its own 10-K gives it,
which also covers years ending in January. Quarter ends come from the year-to-date and
quarterly periods that start or continue the year. Every fact then falls into a slot:
a quarter (Q1 to Q4), a year-to-date total (H1, 9M), the year (FY) or, for instant
values, the end of a quarter (I1 to I4).

On request the calendar also has a provisional year: the one after the last 10-K, while
its 10-Qs are being filed. Its end is projected from the year before; the 10-K replaces
it. Point-in-time views need it, because at a cutoff the current year has no 10-K yet.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from multiverse_pipelines.xbrl.facts import Fact

TOLERANCE_DAYS = 7
YEAR_DAYS = (350, 380)
QUARTER_DAYS = (80, 100)
FIFTY_THREE_WEEKS_DAYS = 368
YTD_SLOTS = {1: "Q1", 2: "H1", 3: "9M"}


@dataclass(frozen=True)
class FiscalYear:
    label: int
    start: date
    end: date
    quarter_ends: tuple[date, date, date, date]
    provisional: bool = False

    @property
    def length(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def fifty_three_weeks(self) -> bool:
        return self.length >= FIFTY_THREE_WEEKS_DAYS

    def quarter(self, number: int) -> tuple[date, date]:
        start = self.start if number == 1 else self.quarter_ends[number - 2] + timedelta(days=1)
        return start, self.quarter_ends[number - 1]


def _years(facts: list[Fact]) -> list[tuple[date, date]]:
    counts: Counter[tuple[date, date]] = Counter(
        (f.start, f.end)
        for f in facts
        if f.start is not None
        and f.form.startswith("10-K")
        and YEAR_DAYS[0] <= (f.length or 0) <= YEAR_DAYS[1]
    )
    chosen: list[tuple[date, date]] = []
    # Most reported first, so a stray overlapping period never displaces a real year.
    for (start, end), _ in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        margin = timedelta(days=TOLERANCE_DAYS)
        overlaps = any(start < e - margin and end > s + margin for s, e in chosen)
        if not overlaps:
            chosen.append((start, end))
    return sorted(chosen, key=lambda period: period[1])


def _labels(facts: list[Fact], ends: set[date]) -> dict[date, int]:
    """The fiscal year each 10-K gives its own primary period."""
    primary: dict[str, Fact] = {}
    for fact in facts:
        if fact.end in ends and fact.fy is not None and fact.form.startswith("10-K"):
            known = primary.get(fact.accession)
            if known is None or fact.end > known.end:
                primary[fact.accession] = fact
    votes: dict[date, Counter[int]] = defaultdict(Counter)
    for fact in primary.values():
        if fact.fy is not None:
            votes[fact.end][fact.fy] += 1
    return {end: counter.most_common(1)[0][0] for end, counter in votes.items()}


def _quarter_ends(facts: list[Fact], start: date, end: date) -> tuple[date, date, date, date]:
    length = (end - start).days + 1
    found: dict[int, Counter[date]] = defaultdict(Counter)
    for fact in facts:
        if fact.start is None or not (start <= fact.end < end):
            continue
        days = fact.length or 0
        if abs((fact.start - start).days) <= TOLERANCE_DAYS:
            k = round(days / (length / 4))
            if k in YTD_SLOTS and abs(days - k * length / 4) <= 15:
                found[k][fact.end] += 1
        elif QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
            k = round((fact.end - start).days / (length / 4))
            if k in (2, 3):
                found[k][fact.end] += 1
    ends = [
        found[k].most_common(1)[0][0]
        if found[k]
        else start + timedelta(days=round(k * length / 4) - 1)
        for k in (1, 2, 3)
    ]
    return (ends[0], ends[1], ends[2], end)


def _projected_end(last: FiscalYear) -> date:
    """The end of the year after ``last``: a month end again, or 52 weeks later."""
    if (last.end + timedelta(days=1)).day == 1:
        year, month = last.end.year + 1, last.end.month
        return date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return last.end + timedelta(days=364)


class FiscalCalendar:
    def __init__(self, years: Iterable[FiscalYear]) -> None:
        self.years = tuple(sorted(years, key=lambda year: year.end))

    @classmethod
    def from_facts(cls, facts: Iterable[Fact], *, provisional: bool = False) -> "FiscalCalendar":
        items = list(facts)
        periods = _years(items)
        labels = _labels(items, {end for _, end in periods})
        years: list[FiscalYear] = []
        used: set[int] = set()
        for start, end in periods:
            label = labels.get(end, end.year)
            if label in used:
                label = end.year
            if label in used:
                continue
            used.add(label)
            years.append(FiscalYear(label, start, end, _quarter_ends(items, start, end)))
        if provisional and years:
            last = max(years, key=lambda year: year.end)
            start = last.end + timedelta(days=1)
            margin = timedelta(days=TOLERANCE_DAYS)
            limit = start + timedelta(days=last.length) + margin
            begun = any(
                f.start is not None
                and f.form.startswith("10-Q")
                and start - margin <= f.start
                and f.end <= limit
                for f in items
            )
            if begun and last.label + 1 not in used:
                end = _projected_end(last)
                ends = _quarter_ends(items, start, end)
                years.append(FiscalYear(last.label + 1, start, end, ends, provisional=True))
        return cls(years)

    def year(self, label: int) -> FiscalYear | None:
        return next((year for year in self.years if year.label == label), None)

    def slot(self, start: date | None, end: date) -> tuple[FiscalYear, str] | None:
        if start is None:
            for year in self.years:
                for number, quarter_end in enumerate(year.quarter_ends, start=1):
                    if abs((end - quarter_end).days) <= 3:
                        return year, f"I{number}"
            return None
        days = (end - start).days + 1
        for year in self.years:
            inside = year.start - timedelta(days=TOLERANCE_DAYS) <= start < year.end
            if not inside or end > year.end + timedelta(days=TOLERANCE_DAYS):
                continue
            quarter = year.length / 4
            if abs((start - year.start).days) <= TOLERANCE_DAYS:
                k = round(days / quarter)
                if k == 4 and YEAR_DAYS[0] <= days <= YEAR_DAYS[1]:
                    return year, "FY"
                if k in YTD_SLOTS and abs(days - k * quarter) <= 15:
                    return year, YTD_SLOTS[k]
                return None
            if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
                number = round((start - year.start).days / quarter) + 1
                if 2 <= number <= 4:
                    return year, f"Q{number}"
            return None
        return None
