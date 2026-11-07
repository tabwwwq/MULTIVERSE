"""The largest companies that file with the SEC, ranked from their own 10-K cover pages.

A ranking by market capitalization needs share prices, and prices need a licence (decision D-06).
The cover of every 10-K states the public float: the market value of shares held by non-affiliates
on the last day of the second fiscal quarter, tagged ``dei:EntityPublicFloat``. It is official and
free, and it is close to market capitalization, with three differences that stay visible:

- it leaves out what insiders hold, so a founder-held company ranks lower than its market value;
- it is up to 18 months old;
- a foreign company that files a 20-F has no such tag, so it cannot be ranked here at all.

Filers make mistakes: a value in thousands tagged as dollars is a thousand times too large. A value
far above total assets and above the company's own earlier floats is scaled back or left out, and
each correction is recorded. Nothing here reads a price.
"""

import json
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from multiverse_contracts.universe import (
    RuleCount,
    UniverseCompany,
    UniverseManifest,
    UniverseStratum,
)
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.sec.universe import FACTS_MEMBER, bulk_file, division, read_tables

SIZE = 500
MAX_AGE = timedelta(days=460)
"""Age of the 10-K, not of the float: a float states the middle of the fiscal year before, and
some filers leave an older date on it. A filer that reports files one every 12 months."""
MAX_FLOAT_TO_ASSETS = 150.0
"""A company worth 150 times its assets is rare; a value in thousands tagged as dollars is not."""
MAX_FLOAT_JUMP = 50.0
"""A float fifty times last year's is a scale error far more often than a triumph."""
MIN_EARLIER = 1_000_000.0
"""Below this an earlier float is itself a mistake, such as 37.4 for 37.4 billion."""
SCALES = (1_000.0, 1_000_000.0)
FUND_SIC = {"6221", "6726", "6770"}
"""Commodity trusts, investment offices and blank-check companies run no business."""
REPORT_FORMS = ("10-K", "10-K/A", "10-KT")
BANK_SIC = range(6000, 6800)
"""Finance, insurance and real estate: no gross margin or capex in the sense the engine assumes."""


@dataclass(frozen=True)
class Candidate:
    cik: str
    name: str
    public_float: float
    float_as_of: date
    filed: date
    assets: float | None
    earlier: float | None
    correction: float = 1.0


def _rows(facts: dict[str, Any], taxonomy: str, concept: str, unit: str) -> list[dict[str, Any]]:
    item = facts.get(taxonomy, {}).get(concept, {})
    rows: list[dict[str, Any]] = item.get("units", {}).get(unit, [])
    return rows


def latest_assets(facts: dict[str, Any]) -> float | None:
    rows = _rows(facts, "us-gaap", "Assets", "USD")
    if not rows:
        return None
    return float(max(rows, key=lambda row: (row["end"], row.get("filed", "")))["val"])


def candidate_from(cik: str, payload: dict[str, Any], today: date) -> Candidate | None:
    """The newest float of a recent 10-K, and the value before it for comparison."""
    facts = payload.get("facts", {})
    rows = [
        row
        for row in _rows(facts, "dei", "EntityPublicFloat", "USD")
        if row.get("form") in REPORT_FORMS and row.get("val", 0) > 0
    ]
    if not rows:
        return None
    rows.sort(key=lambda row: (row.get("filed", ""), row["end"]))
    last = rows[-1]
    as_of = date.fromisoformat(last["end"])
    if today - date.fromisoformat(last["filed"]) > MAX_AGE:
        return None
    earlier = [row["val"] for row in rows if row.get("filed", "") < last.get("filed", "")]
    return Candidate(
        cik=cik,
        name=str(payload.get("entityName") or ""),
        public_float=float(last["val"]),
        float_as_of=as_of,
        filed=date.fromisoformat(last["filed"]),
        assets=latest_assets(facts),
        earlier=float(earlier[-1]) if earlier else None,
    )


def _plausible(value: float, company: Candidate) -> bool:
    """A bank has large assets, so its own earlier float has to agree as well."""
    earlier = company.earlier
    if earlier is not None and earlier >= MIN_EARLIER and value > earlier * MAX_FLOAT_JUMP:
        return False
    if company.assets is None or company.assets <= 0:
        return True
    return value <= company.assets * MAX_FLOAT_TO_ASSETS


def corrected(company: Candidate) -> Candidate | None:
    """The value as filed when it is plausible, else scaled down, else nothing to rank."""
    if _plausible(company.public_float, company):
        return company
    for scale in SCALES:
        value = company.public_float / scale
        if _plausible(value, company):
            return replace(company, public_float=value, correction=scale)
    return None


def scan_floats(
    facts_zip: Path,
    today: date,
    progress: Callable[[int, int], None] | None = None,
) -> list[Candidate]:
    """Every filer with a recent float. Reads all of Company Facts: minutes, not seconds."""
    found: list[Candidate] = []
    with zipfile.ZipFile(facts_zip) as facts:
        names = sorted(n for n in facts.namelist() if FACTS_MEMBER.fullmatch(n))
        for number, name in enumerate(names, start=1):
            match = FACTS_MEMBER.fullmatch(name)
            if match is None:
                continue
            item = candidate_from(match[1], json.loads(facts.read(name)), today)
            if item is not None:
                found.append(item)
            if progress is not None:
                progress(number, len(names))
    return found


@dataclass(frozen=True)
class Listing:
    """What the submissions file adds: who the filer is and where it trades."""

    sic: str | None
    tickers: tuple[str, ...]
    exchanges: tuple[str, ...]
    entity_type: str
    fiscal_year_end: str | None
    country: str | None
    name: str
    xbrl_10k: int
    xbrl_10q: int
    first_xbrl_filed: date | None
    last_filed: date | None


def listing_from(submissions: zipfile.ZipFile, cik: str) -> Listing | None:
    try:
        main, tables = read_tables(submissions, cik)
    except KeyError:
        return None
    annual = quarterly = 0
    first: date | None = None
    last: date | None = None
    for table in tables:
        for form, filed, xbrl in zip(
            table["form"], table["filingDate"], table["isXBRL"], strict=True
        ):
            day = date.fromisoformat(filed)
            last = day if last is None else max(last, day)
            if xbrl and form in ("10-K", "10-Q"):
                annual += form == "10-K"
                quarterly += form == "10-Q"
                first = day if first is None else min(first, day)
    business = (main.get("addresses") or {}).get("business") or {}
    code = business.get("stateOrCountry")
    return Listing(
        sic=str(main.get("sic") or "") or None,
        tickers=tuple(t for t in main.get("tickers") or [] if t),
        exchanges=tuple(e for e in main.get("exchanges") or [] if e),
        entity_type=str(main.get("entityType") or ""),
        fiscal_year_end=main.get("fiscalYearEnd"),
        # A state keeps its code as its description; a country gets its name.
        country=code if code and code != business.get("stateOrCountryDescription") else None,
        name=str(main.get("name") or ""),
        xbrl_10k=annual,
        xbrl_10q=quarterly,
        first_xbrl_filed=first,
        last_filed=last,
    )


def save_floats(found: Sequence[Candidate], path: Path) -> None:
    """The scan reads every filer: minutes that a second ranking need not spend."""
    rows = [
        {**asdict(item), "float_as_of": str(item.float_as_of), "filed": str(item.filed)}
        for item in found
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


def load_floats(path: Path) -> list[Candidate]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        Candidate(
            **{
                **row,
                "float_as_of": date.fromisoformat(row["float_as_of"]),
                "filed": date.fromisoformat(row["filed"]),
            }
        )
        for row in rows
    ]


def with_exchange_list(
    listing: Listing, listed: dict[str, list[tuple[str, str]]], cik: str
) -> Listing:
    """The submissions file leaves tickers empty for some large filers, such as Exxon Mobil."""
    found = listed.get(cik)
    if listing.tickers or not found:
        return listing
    return replace(
        listing, tickers=tuple(t for t, _ in found), exchanges=tuple(e for _, e in found)
    )


def read_exchange_list(path: Path) -> dict[str, list[tuple[str, str]]]:
    """``company_tickers_exchange.json`` of the SEC: CIK, name, ticker, exchange."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = payload["fields"]
    found: dict[str, list[tuple[str, str]]] = {}
    for values in payload["data"]:
        row = dict(zip(fields, values, strict=True))
        if row["ticker"] and row["exchange"]:
            found.setdefault(f"{row['cik']:010d}", []).append((row["ticker"], row["exchange"]))
    return found


def is_fund(listing: Listing) -> bool:
    return listing.sic in FUND_SIC


def financial(sic: str | None) -> bool:
    return sic is not None and sic.isdigit() and int(sic) in BANK_SIC


def _group_key(company: Candidate) -> tuple[str, float]:
    """Co-registrants file one cover page: the same float means one company, listed once."""
    return (company.float_as_of.isoformat(), round(company.public_float, -3))


def ranked(
    candidates: Iterable[Candidate],
    listings: dict[str, Listing],
    size: int = SIZE,
) -> list[Candidate]:
    """Largest first: operating companies, once each.

    A public float means traded shares, even where the files name no ticker, as with Exxon Mobil.
    Filers round their floats, so an equal float proves nothing between two listed companies: it
    only drops a registrant without a ticker, which shares the cover page of its parent.
    """

    def order(company: Candidate) -> tuple[float, bool, str]:
        listing = listings.get(company.cik)
        return (-company.public_float, not (listing and listing.tickers), company.cik)

    chosen: list[Candidate] = []
    floats: set[tuple[str, float]] = set()
    ciks: set[str] = set()
    for company in sorted(candidates, key=order):
        listing = listings.get(company.cik)
        if listing is None or company.cik in ciks or is_fund(listing) or listing.xbrl_10k == 0:
            continue
        if listing.sic is None or listing.first_xbrl_filed is None or listing.last_filed is None:
            continue
        key = _group_key(company)
        if key in floats and not listing.tickers:
            continue
        floats.add(key)
        ciks.add(company.cik)
        chosen.append(company)
    return chosen[:size]


def corrections_of(companies: Sequence[Candidate]) -> list[Candidate]:
    return [company for company in companies if company.correction != 1.0]


def top_manifest(
    *,
    universe_id: str,
    chosen: Sequence[Candidate],
    listings: dict[str, Listing],
    scanned: int,
    plausible: int,
    rows: Sequence[RawObject],
) -> UniverseManifest:
    companies = []
    for rank, company in enumerate(chosen, start=1):
        listing = listings[company.cik]
        if listing.sic is None or listing.first_xbrl_filed is None or listing.last_filed is None:
            raise ValueError(f"CIK {company.cik} lacks the fields of a ranked company")
        companies.append(
            UniverseCompany(
                cik=company.cik,
                name=listing.name or company.name,
                sic=listing.sic,
                division=division(listing.sic)[0],
                xbrl_10k=listing.xbrl_10k,
                xbrl_10q=listing.xbrl_10q,
                first_xbrl_filed=listing.first_xbrl_filed,
                last_filed=listing.last_filed,
                deregistered=False,
                candidate=False,
                rank=rank,
                public_float_usd=company.public_float,
                float_as_of=company.float_as_of,
                float_correction=company.correction,
                tickers=listing.tickers,
                exchanges=listing.exchanges,
                country=listing.country,
                fiscal_year_end=listing.fiscal_year_end,
                financial=financial(listing.sic),
            )
        )
    counts = Counter(company.division for company in companies)
    return UniverseManifest(
        universe_id=universe_id,
        decision=(
            "D-14 (owner, 2026-11-06): real companies, the largest by value; ranked by the public "
            "float of the 10-K cover, because market prices need a licence (D-06)"
        ),
        seed=0,
        size=len(companies),
        created_at=datetime.now(UTC),
        sources=tuple(bulk_file(row) for row in rows),
        scanned=scanned,
        rules=(
            RuleCount(rule="A public float on a 10-K of the last 18 months", remaining=plausible),
            RuleCount(
                rule="Traded, not a fund, one row per cover page, largest first",
                remaining=len(companies),
            ),
        ),
        strata=tuple(
            UniverseStratum(
                division=key,
                title=division(next(c.sic for c in companies if c.division == key))[1],
                eligible=count,
                quota=count,
                selected=count,
            )
            for key, count in sorted(counts.items())
        ),
        companies=tuple(sorted(companies, key=lambda company: company.cik)),
    )
