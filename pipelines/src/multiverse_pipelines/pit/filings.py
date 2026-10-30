"""The filing index of one company, from its archived submissions files.

The submissions file lists every filing with its form, filing date, report date and
EDGAR acceptance time; older filings sit in paged files next to it. From it come the
moment each filing became public, which reports were public at a cutoff, whether the
company had filed to deregister, and its name over time.

Only the name has an official history here (``formerNames`` with dates). Tickers,
exchanges and the SIC code are current values: they apply from the moment they were
observed and are unknown before it, so an old cutoff never sees today's ticker or sector.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from multiverse_contracts.pit import (
    EntityAttribute,
    EntityAttributeName,
    SourceTiming,
    TimePrecision,
)
from multiverse_pipelines.pit.clock import eastern_date, knowledge_time
from multiverse_pipelines.sec.cik import cik10

PERIODIC_FORMS = frozenset({"10-Q", "10-K", "10-QT", "10-KT"})
DEREGISTRATION_PREFIXES = ("15-", "15F-")


@dataclass(frozen=True)
class Filing:
    accession: str
    form: str
    filing_date: date
    report_date: date | None
    accepted: datetime | None
    known_at: datetime
    precision: TimePrecision
    xbrl: bool

    @property
    def base_form(self) -> str:
        return self.form.removesuffix("/A")

    @property
    def amended(self) -> bool:
        return self.form.endswith("/A")

    @property
    def periodic(self) -> bool:
        return self.base_form in PERIODIC_FORMS

    @property
    def deregistration(self) -> bool:
        return self.form.startswith(DEREGISTRATION_PREFIXES)

    def timing(self) -> SourceTiming:
        return SourceTiming(
            accession=self.accession, known_at=self.known_at, precision=self.precision
        )


def _accepted(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def filings_from_tables(tables: Iterable[Mapping[str, Any]]) -> list[Filing]:
    """Filings of the main submissions file (``filings.recent``) and its paged files."""
    found: dict[str, Filing] = {}
    for table in tables:
        columns = zip(
            table["accessionNumber"],
            table["form"],
            table["filingDate"],
            table["reportDate"],
            table["acceptanceDateTime"],
            table["isXBRL"],
            strict=True,
        )
        for accession, form, filed, report, accepted_text, xbrl in columns:
            filing_date = date.fromisoformat(filed)
            accepted = _accepted(accepted_text)
            known_at, precision = knowledge_time(filing_date, accepted)
            found.setdefault(
                accession,
                Filing(
                    accession=accession,
                    form=form,
                    filing_date=filing_date,
                    report_date=date.fromisoformat(report) if report else None,
                    accepted=accepted,
                    known_at=known_at,
                    precision=precision,
                    xbrl=bool(xbrl),
                ),
            )
    return sorted(found.values(), key=lambda f: (f.known_at, f.accession))


class FilingIndex:
    def __init__(self, filings: Iterable[Filing]) -> None:
        self.filings = tuple(sorted(filings, key=lambda f: (f.known_at, f.accession)))
        self._by_accession = {filing.accession: filing for filing in self.filings}

    def get(self, accession: str) -> Filing | None:
        return self._by_accession.get(accession)

    def timing(self, accession: str, filed: date) -> SourceTiming:
        """When a fact's filing became public; the end of its filing date if not indexed."""
        filing = self.get(accession)
        if filing is not None:
            return filing.timing()
        known_at, precision = knowledge_time(filed, None)
        return SourceTiming(accession=accession, known_at=known_at, precision=precision)

    def known(self, at: datetime) -> list[Filing]:
        return [filing for filing in self.filings if filing.known_at <= at]

    def reports(self, at: datetime) -> list[Filing]:
        """Periodic reports with a report date that were public at a moment."""
        return [f for f in self.known(at) if f.periodic and f.report_date is not None]

    def first_filing(self) -> Filing | None:
        return min(self.filings, key=lambda f: f.filing_date, default=None)

    def deregistered(self, at: datetime) -> Filing | None:
        """The Form 15 public at a moment with no periodic report after it, if any.

        A Form 15 can also end the registration of one class of securities (debt, a
        share class); a later 10-Q or 10-K shows the company still reports.
        """
        last: Filing | None = None
        for filing in self.known(at):
            if filing.deregistration:
                last = filing
            elif filing.periodic and last is not None and filing.known_at > last.known_at:
                last = None
        return last


def attributes_from_submissions(
    cik: str, doc: Mapping[str, Any], observed_at: datetime, first_filing: date | None
) -> list[EntityAttribute]:
    """Name history (official dates) and the current ticker, exchange and SIC code."""
    cik = cik10(cik)
    found: list[EntityAttribute] = []
    former = sorted(doc.get("formerNames") or [], key=lambda item: item["from"])
    for item in former:
        start = eastern_date(_moment(item["from"]))
        # Some names are listed for one day only (from = to): such a name held that day.
        end = max(eastern_date(_moment(item["to"])), start + timedelta(days=1))
        found.append(
            EntityAttribute(
                cik=cik,
                attribute=EntityAttributeName.NAME,
                value=item["name"],
                effective_from=start,
                effective_to=end,
                observed_at=observed_at,
                source="SEC submissions: formerNames with dates",
            )
        )
    since = eastern_date(_moment(former[-1]["to"])) if former else first_filing
    if doc.get("name"):
        found.append(
            EntityAttribute(
                cik=cik,
                attribute=EntityAttributeName.NAME,
                value=doc["name"],
                effective_from=since,
                observed_at=observed_at,
                source=(
                    "SEC submissions: current name, since the last former name ended"
                    if former
                    else "SEC submissions: current name, no former names since the first filing"
                ),
            )
        )
    current = "SEC submissions: current value only, no history in the archive"
    for ticker in doc.get("tickers") or []:
        found.append(_current(cik, EntityAttributeName.TICKER, ticker, observed_at, current))
    for exchange in {e for e in doc.get("exchanges") or [] if e}:
        found.append(_current(cik, EntityAttributeName.EXCHANGE, exchange, observed_at, current))
    if doc.get("sic"):
        found.append(_current(cik, EntityAttributeName.SIC, str(doc["sic"]), observed_at, current))
    return found


def _moment(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _current(
    cik: str, attribute: EntityAttributeName, value: str, observed_at: datetime, source: str
) -> EntityAttribute:
    return EntityAttribute(
        cik=cik, attribute=attribute, value=value, observed_at=observed_at, source=source
    )


def attribute_as_of(
    records: Sequence[EntityAttribute], cik: str, attribute: EntityAttributeName, at: datetime
) -> tuple[tuple[str, ...], str | None]:
    """Values of one attribute at a moment, or none and the reason."""
    day = eastern_date(at)
    mine = [r for r in records if r.cik == cik10(cik) and r.attribute is attribute]
    dated = sorted(
        r.value
        for r in mine
        if r.effective_from is not None
        and r.effective_from <= day
        and (r.effective_to is None or day < r.effective_to)
    )
    if dated:
        return tuple(dated), None
    current = sorted(r.value for r in mine if r.effective_from is None and r.observed_at <= at)
    if current:
        return tuple(current), None
    if any(r.effective_from is None for r in mine):
        seen = min(r.observed_at for r in mine if r.effective_from is None)
        return (), f"only the value observed on {eastern_date(seen)} is known, not its history"
    return (), f"no {attribute.value} recorded for this date"


def resolve_ticker(records: Sequence[EntityAttribute], ticker: str, at: datetime) -> list[str]:
    """Companies that used a ticker at a moment (a ticker can pass to another company)."""
    ciks = sorted({r.cik for r in records if r.attribute is EntityAttributeName.TICKER})
    return [
        cik
        for cik in ciks
        if ticker in attribute_as_of(records, cik, EntityAttributeName.TICKER, at)[0]
    ]
