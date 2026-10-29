"""Sample coverage: what the archived files of each candidate hold, checked against the catalog.

Nothing is normalized here (that is Stage 11). The report counts filings by form, the
facts per taxonomy and, for the seven V2 metrics, the US-GAAP concepts a company used
and how many distinct periods in USD its 10-K and 10-Q filings report.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from multiverse_contracts.sources import CompanyCandidate
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.ingest import COMPANYFACTS, SUBMISSIONS
from multiverse_pipelines.sec.validate import load_json

# Several concepts per metric: companies moved, for example, from SalesRevenueNet to
# RevenueFromContractWithCustomerExcludingAssessedTax when ASC 606 took effect in 2018,
# and some report capex or debt under broader concepts. A draft for Stage 11, which
# decides the concept of every value; here it only measures what the files hold.
METRIC_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ),
    "operating_income": ("OperatingIncomeLoss",),
    "research_and_development": ("ResearchAndDevelopmentExpense",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    "long_term_debt": (
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
}
PERIODIC_FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"})
FOREIGN_FORMS = frozenset({"20-F", "40-F", "6-K"})


class Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MetricCoverage(Row):
    concepts: tuple[str, ...]
    periods: int
    first_end: date | None
    last_end: date | None


class CompanyCoverage(Row):
    rank: int
    cik: str
    name: str
    found: bool
    entity_name: str | None = None
    tickers_observed: tuple[str, ...] = ()
    sic_observed: str | None = None
    sic_matches: bool | None = None
    fiscal_year_end_matches: bool | None = None
    filings: int = 0
    pages_listed: int = 0
    pages_archived: int = 0
    forms: dict[str, int] = {}
    foreign_forms: int = 0
    first_filed: date | None = None
    last_filed: date | None = None
    facts_by_taxonomy: dict[str, int] = {}
    us_gaap_concepts: int = 0
    accessions: int = 0
    metrics: dict[str, MetricCoverage] = {}


def _metric(us_gaap: Mapping[str, Any], concepts: Iterable[str]) -> MetricCoverage:
    present: list[str] = []
    periods: set[tuple[str | None, str]] = set()
    for concept in concepts:
        if concept not in us_gaap:
            continue
        present.append(concept)
        for value in us_gaap[concept].get("units", {}).get("USD", []):
            if value.get("form") in PERIODIC_FORMS:
                periods.add((value.get("start"), str(value["end"])))
    ends = sorted(date.fromisoformat(end[:10]) for _, end in periods)
    return MetricCoverage(
        concepts=tuple(present),
        periods=len(periods),
        first_end=ends[0] if ends else None,
        last_end=ends[-1] if ends else None,
    )


def company_coverage(archive: RawArchive, candidate: CompanyCandidate) -> CompanyCoverage:
    key = f"CIK{candidate.cik}"
    submissions = archive.latest(SUBMISSIONS, key)
    facts_row = archive.latest(COMPANYFACTS, key)
    if submissions is None or facts_row is None:
        return CompanyCoverage(
            rank=candidate.rank, cik=candidate.cik, name=candidate.name, found=False
        )

    doc = load_json(archive.root / submissions.path)
    tables = [doc["filings"]["recent"]]
    pages = [page["name"] for page in doc["filings"].get("files", [])]
    for name in pages:
        number = name.rsplit("-", 1)[-1].removesuffix(".json")
        page = archive.latest(SUBMISSIONS, f"{key}/submissions-{number}")
        if page is not None:
            tables.append(load_json(archive.root / page.path))
    forms = Counter(str(form) for table in tables for form in table["form"])
    filed = sorted(date.fromisoformat(str(d)[:10]) for table in tables for d in table["filingDate"])

    facts = load_json(archive.root / facts_row.path)["facts"]
    us_gaap = facts.get("us-gaap", {})
    accessions = {
        str(value["accn"])
        for concepts in facts.values()
        for concept in concepts.values()
        for values in concept["units"].values()
        for value in values
    }
    return CompanyCoverage(
        rank=candidate.rank,
        cik=candidate.cik,
        name=candidate.name,
        found=True,
        entity_name=doc.get("name"),
        tickers_observed=tuple(doc.get("tickers") or ()),
        sic_observed=doc.get("sic"),
        sic_matches=doc.get("sic") == candidate.sic,
        fiscal_year_end_matches=doc.get("fiscalYearEnd") == candidate.fiscal_year_end,
        filings=sum(forms.values()),
        pages_listed=len(pages),
        pages_archived=len(tables) - 1,
        forms={form: forms[form] for form in ("10-K", "10-Q", "10-K/A", "10-Q/A") if forms[form]},
        foreign_forms=sum(n for form, n in forms.items() if form in FOREIGN_FORMS),
        first_filed=filed[0] if filed else None,
        last_filed=filed[-1] if filed else None,
        facts_by_taxonomy={
            taxonomy: sum(len(values) for c in concepts.values() for values in c["units"].values())
            for taxonomy, concepts in sorted(facts.items())
        },
        us_gaap_concepts=len(us_gaap),
        accessions=len(accessions),
        metrics={name: _metric(us_gaap, concepts) for name, concepts in METRIC_CONCEPTS.items()},
    )


def build_coverage(
    archive: RawArchive, candidates: Sequence[CompanyCandidate]
) -> list[CompanyCoverage]:
    return [company_coverage(archive, candidate) for candidate in candidates]


def _years(metric: MetricCoverage) -> str:
    if metric.first_end is None or metric.last_end is None:
        return "none"
    return f"{metric.periods} ({metric.first_end.year}-{metric.last_end.year})"


def to_markdown(rows: Sequence[CompanyCoverage]) -> str:
    """Two tables: filings and facts per company, then periods per metric."""
    lines = [
        "| # | Company | SIC, FYE as catalog | Filings | 10-K | 10-Q | Filed | us-gaap concepts "
        "| Taxonomies | Filings with facts |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        if not row.found:
            lines.append(f"| {row.rank} | {row.name} | not archived | | | | | | | |")
            continue
        same = "yes" if row.sic_matches and row.fiscal_year_end_matches else "**no**"
        span = f"{row.first_filed:%Y-%m} to {row.last_filed:%Y-%m}" if row.first_filed else ""
        taxonomies = ", ".join(row.facts_by_taxonomy)
        lines.append(
            f"| {row.rank} | {row.name} | {same} | {row.filings} | {row.forms.get('10-K', 0)} "
            f"| {row.forms.get('10-Q', 0)} | {span} | {row.us_gaap_concepts} | {taxonomies} "
            f"| {row.accessions} |"
        )
    names = list(METRIC_CONCEPTS)
    lines += ["", "| # | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for row in rows:
        if row.found:
            cells = " | ".join(_years(row.metrics[name]) for name in names)
            lines.append(f"| {row.rank} | {cells} |")
    return "\n".join(lines) + "\n"
