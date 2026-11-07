"""Real companies for the screens: filings, today's forecast and a case to run (Stage 24b).

Reads the warehouse, the live forecast and the forecasting dataset, and writes one small JSON per
company into ``data/companies``, plus an index. Cases are larger and hold assumptions, so they stay
in ``<data dir>/cases``, where the worker finds them.

A company that cannot have a case still gets a file: a bank has no EBITDA, and a file that says so
is better than a company missing from the list.
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from multiverse_contracts.companies import (
    AccountingStandard,
    Company,
    CompanyDossier,
    CoverageEntry,
    DataQualityFlag,
    DatedName,
    FilingForm,
    FilingReference,
    QualitySeverity,
    Sector,
    SupportStatus,
    TickerListing,
)
from multiverse_contracts.forecasting import ForecastTarget, LiveCompany, LiveForecast
from multiverse_contracts.metrics import (
    Lineage,
    LineageMethod,
    MetricValue,
    Period,
    PeriodType,
)
from multiverse_contracts.pit import PanelCell
from multiverse_contracts.primitives import DataOrigin, MeasureUnit, Quantity, ValueKind
from multiverse_contracts.real import RankEvidence, RealCompany, RealCompanyRow, RealIndex
from multiverse_contracts.universe import UniverseCompany, UniverseManifest
from multiverse_forecast.data import Dataset
from multiverse_forecast.probabilistic import median_of
from multiverse_pipelines.pit.clock import day_end
from multiverse_pipelines.pit.panel import Panel, build_panel
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_simulation.casebuild import build_case

QUARTERS = 12
MIN_QUARTERS = 8
PANEL = (
    "revenue",
    "ebitda",
    "free_cash_flow",
    "rnd",
    "cash",
    "long_term_debt",
    "long_term_debt_noncurrent",
    "debt_current",
)
SHOWN = {
    "revenue": "revenue",
    "ebitda": "ebitda_calculated",
    "free_cash_flow": "fcf_simple",
    "rnd": "rnd_expense",
}
FORMS = {
    "10-K": FilingForm.FORM_10K,
    "10-KT": FilingForm.FORM_10K,
    "10-Q": FilingForm.FORM_10Q,
    "10-QT": FilingForm.FORM_10Q,
    "10-K/A": FilingForm.FORM_10K_A,
    "10-Q/A": FilingForm.FORM_10Q_A,
}
QUARTER_OF = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
COUNTRIES = {
    "2M": "DE",
    "C3": "AU",
    "D0": "BM",
    "E9": "KY",
    "F4": "CN",
    "I0": "FR",
    "K3": "HK",
    "L2": "IE",
    "L3": "IL",
    "M0": "JP",
    "N4": "LU",
    "P7": "NL",
    "U0": "SG",
    "V8": "CH",
    "X0": "GB",
}
SECTOR_RANGES: tuple[tuple[int, int, Sector], ...] = (
    (3674, 3674, Sector.SEMICONDUCTORS),
    (3841, 3851, Sector.MEDICAL_DEVICES),
    (3820, 3829, Sector.INSTRUMENTS),
    (3500, 3569, Sector.INDUSTRIAL_MACHINERY),
    (3570, 3579, Sector.TECHNOLOGY_HARDWARE),
    (3600, 3699, Sector.TECHNOLOGY_HARDWARE),
    (3700, 3799, Sector.TRANSPORT_EQUIPMENT),
    (7370, 7379, Sector.SOFTWARE),
    (2830, 2836, Sector.HEALTHCARE),
    (8000, 8099, Sector.HEALTHCARE),
    (4900, 4999, Sector.UTILITIES),
    (4800, 4899, Sector.MEDIA_TELECOM),
    (7800, 7999, Sector.MEDIA_TELECOM),
    (2700, 2799, Sector.MEDIA_TELECOM),
    (4000, 4799, Sector.LOGISTICS),
    (1000, 1499, Sector.ENERGY_MINING),
    (2900, 2999, Sector.ENERGY_MINING),
    (5000, 5999, Sector.RETAIL_WHOLESALE),
    (6000, 6799, Sector.FINANCE),
    (2000, 2199, Sector.CONSUMER_GOODS),
    (2200, 2399, Sector.CONSUMER_GOODS),
)


MARGIN_TARGETS = (
    ForecastTarget.EBITDA_MARGIN,
    ForecastTarget.OPERATING_MARGIN,
    ForecastTarget.FCF_MARGIN,
)
STAND_INS = frozenset({"ebitda_basis", "d_and_a_missing", "capex_missing", "margin_source"})


def sector_of(sic: str) -> Sector:
    code = int(sic) if sic.isdigit() else 0
    for low, high, sector in SECTOR_RANGES:
        if low <= code <= high:
            return sector
    return Sector.OTHER


def company_id_of(cik: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sec:{cik}"))


def country_of(company: UniverseCompany) -> str:
    if company.country is None:
        return "US"
    if company.country.startswith(("A", "B")):
        return "CA"
    return COUNTRIES.get(company.country, "ZZ")


def company_of(item: UniverseCompany) -> Company:
    listings: tuple[TickerListing, ...] = ()
    if item.tickers and item.exchanges:
        listings = (
            TickerListing(
                ticker=item.tickers[0].upper(),
                exchange=item.exchanges[0],
                valid_from=item.first_xbrl_filed,
            ),
        )
    end = item.fiscal_year_end or "1231"
    return Company(
        company_id=company_id_of(item.cik),
        cik=item.cik,
        names=(DatedName(name=item.name, valid_from=item.first_xbrl_filed),),
        listings=listings,
        sector=sector_of(item.sic),
        country=country_of(item),
        reporting_currency="USD",
        accounting_standard=AccountingStandard.US_GAAP,
        fiscal_year_end=f"{end[:2]}-{end[2:]}" if end[2:] <= "31" else "12-31",
        data_origin=DataOrigin.EMPIRICAL,
    )


def _source(panel: Panel, cell: PanelCell) -> tuple[str, Sequence[str]]:
    """The form of the filing and the concepts behind a value."""
    found = panel.sources.get((cell.cik, cell.calendar_quarter, cell.metric))
    if found is None or not found.value.sources:
        return "10-Q", (cell.concept or "us-gaap:Revenues",)
    return found.value.sources[0].form, tuple(sorted({s.concept for s in found.value.sources}))


def _filing_id(accession: str) -> str:
    return f"sec-{accession}"


def _url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"


def _period(cell: PanelCell) -> Period | None:
    if cell.fiscal_year is None or cell.fiscal_period is None or cell.period_end is None:
        return None
    quarter = QUARTER_OF.get(cell.fiscal_period.value)
    if quarter is None:
        return None
    return Period(
        type=PeriodType.FISCAL_QUARTER,
        end_date=cell.period_end,
        fiscal_year=cell.fiscal_year,
        fiscal_quarter=quarter,
    )


def _money(value: Decimal | str) -> Quantity:
    return Quantity(value=str(value), unit=MeasureUnit.CURRENCY, currency="USD")


def dossier_of(
    warehouse: Warehouse, item: UniverseCompany, as_of: datetime, extra: Sequence[DataQualityFlag]
) -> CompanyDossier:
    """Twelve quarters of what the filings say, with each value tied to its filing."""
    panel = build_panel(
        warehouse, [item.cik], day_end(as_of.date()), quarters=QUARTERS + 1, metrics=PANEL
    )
    filings: dict[str, FilingReference] = {}
    values: list[MetricValue] = []
    cells = {(cell.metric, cell.lag): cell for cell in panel.cells}

    def cite(cell: PanelCell, form: str) -> str | None:
        if cell.accession is None or cell.known_from is None or cell.period_end is None:
            return None
        if form not in FORMS or cell.known_from.date() < cell.period_end:
            return None
        key = _filing_id(cell.accession)
        known = filings.get(key)
        end = max(cell.period_end, known.period_end) if known else cell.period_end
        filings[key] = FilingReference(
            filing_id=key,
            form=FORMS[form],
            accession_number=cell.accession,
            period_end=end,
            filed_at=cell.known_from,
            url=_url(item.cik, cell.accession),
            data_origin=DataOrigin.EMPIRICAL,
        )
        return key

    for (metric, _lag), cell in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        shown = SHOWN.get(metric)
        period = _period(cell)
        if shown is None or period is None or not cell.mask or cell.value is None:
            continue
        form, concepts = _source(panel, cell)
        source = cite(cell, form)
        if source is None or cell.method is None or (cell.currency or "USD") != "USD":
            continue
        values.append(
            MetricValue(
                metric=shown,
                quantity=_money(cell.value),
                kind=ValueKind.OBSERVED,
                data_origin=DataOrigin.EMPIRICAL,
                period=period,
                as_of=as_of,
                source_ids=(source,),
                lineage=Lineage(
                    concepts=tuple(concepts),
                    method=cell.method,
                    formula="reported value" if cell.method is LineageMethod.CALCULATED else None,
                ),
            )
        )
    for lag in range(QUARTERS + 1):
        cash = cells.get(("cash", lag))
        debt = next(
            (
                cells[(name, lag)]
                for name in ("long_term_debt", "long_term_debt_noncurrent")
                if (name, lag) in cells and cells[(name, lag)].value is not None
            ),
            None,
        )
        if cash is None or cash.value is None or debt is None or debt.value is None:
            continue
        current = cells.get(("debt_current", lag))
        total = Decimal(debt.value)
        if debt.metric == "long_term_debt_noncurrent" and current and current.value:
            total += Decimal(current.value)
        form, concepts = _source(panel, cash)
        source = cite(cash, form)
        if source is None or cash.period_end is None:
            continue
        values.append(
            MetricValue(
                metric="net_debt",
                quantity=_money(total - Decimal(cash.value)),
                kind=ValueKind.OBSERVED,
                data_origin=DataOrigin.EMPIRICAL,
                period=Period(type=PeriodType.INSTANT, end_date=cash.period_end),
                as_of=as_of,
                source_ids=(source,),
                lineage=Lineage(
                    concepts=tuple(concepts),
                    method=LineageMethod.CALCULATED,
                    formula="long-term debt plus current debt minus cash",
                ),
            )
        )
    known = {metric: sum(v.metric == metric for v in values) for metric in SHOWN.values()}
    revenue = known["revenue"]
    supported = revenue >= MIN_QUARTERS
    return CompanyDossier(
        company=company_of(item),
        support_status=SupportStatus.SUPPORTED if supported else SupportStatus.INSUFFICIENT_HISTORY,
        support_reason=None
        if supported
        else f"{revenue} quarters of revenue in filings; {MIN_QUARTERS} are needed.",
        as_of=as_of,
        filings=tuple(sorted(filings.values(), key=lambda filing: filing.filed_at)),
        values=tuple(values),
        coverage=tuple(
            CoverageEntry(
                metric=metric, quarters_valid=min(count, QUARTERS), quarters_expected=QUARTERS
            )
            for metric, count in known.items()
        ),
        quality_flags=tuple(extra),
    )


def flags_of(item: UniverseCompany) -> list[DataQualityFlag]:
    found = []
    if item.float_correction > 1:
        found.append(
            DataQualityFlag(
                code="float_scale_error",
                severity=QualitySeverity.WARNING,
                message=(
                    f"The public float on the 10-K cover was {item.float_correction:,.0f} times "
                    "too large for the company's assets, and is divided by that for the ranking."
                ),
            )
        )
    if item.financial:
        found.append(
            DataQualityFlag(
                code="financial_company",
                severity=QualitySeverity.WARNING,
                message=(
                    "Banks, insurers and REITs report no EBITDA or capex in the sense the engine "
                    "assumes: margins may be missing and no simulation runs here."
                ),
            )
        )
    return found


def medians_of(live: LiveCompany) -> dict[str, dict[int, float]]:
    """Medians of the margins a case can start from, by target and horizon."""
    found: dict[str, dict[int, float]] = {}
    for target in MARGIN_TARGETS:
        for horizon in (4, 8):
            value = median_of(live, target, horizon)
            if value is not None:
                found.setdefault(target.value, {})[horizon] = float(value)
    return found


def case_for(
    warehouse: Warehouse,
    ds: Dataset,
    live: LiveCompany | None,
    item: UniverseCompany,
    origins: Sequence[date],
    as_of: date,
    model_id: str,
    gdp: Mapping[int, float],
    folder: Path,
) -> tuple[str | None, str | None]:
    """The case id, or why there is none. Companies off the calendar fall back a quarter."""
    if item.financial:
        return (
            None,
            "No simulation for banks, insurers and REITs: there is no EBITDA to start from.",
        )
    if live is None:
        return None, "No forecast, so no central path to start from."
    medians = medians_of(live)
    problem = "no quarter to start from"
    for origin in origins:
        try:
            case = build_case(
                warehouse,
                ds,
                medians,
                item.cik,
                item.name,
                origin,
                model_id,
                gdp,
                as_of,
            )
        except (ValueError, IndexError, KeyError) as error:
            problem = str(error)
            continue
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{case.case_id}.json").write_text(
            case.model_dump_json(), encoding="utf-8", newline="\n"
        )
        notes = [note.note for note in case.inputs if note.name in STAND_INS and note.note]
        return case.case_id, " ".join(notes)[:900] or None
    return None, f"A case needs more than the filings give: {problem}"[:900]


def export(
    universe: UniverseManifest,
    warehouse: Warehouse,
    ds: Dataset,
    forecast: LiveForecast,
    as_of: datetime,
    origins: Sequence[date],
    out: Path,
    cases: Path,
    gdp: Mapping[int, float],
    progress: Callable[[int, int], None] | None = None,
) -> RealIndex:
    by_cik = {company.cik: company for company in forecast.companies}
    rows = []
    out.mkdir(parents=True, exist_ok=True)
    for number, item in enumerate(universe.companies, start=1):
        if item.rank is None or item.public_float_usd is None or item.float_as_of is None:
            raise ValueError(f"{item.cik} has no rank: this export is for a ranked universe")
        dossier = dossier_of(warehouse, item, as_of, flags_of(item))
        live = by_cik.get(item.cik)
        if live is not None and not live.bands:
            live = None
        case_id, case_note = case_for(
            warehouse, ds, live, item, origins, as_of.date(), forecast.forecast_id, gdp, cases
        )
        evidence = RankEvidence(
            rank=item.rank,
            public_float_usd=item.public_float_usd,
            float_as_of=item.float_as_of,
            float_correction=item.float_correction,
        )
        record = RealCompany(
            dossier=dossier,
            evidence=evidence,
            financial=item.financial,
            forecast=live,
            forecast_note=None
            if live
            else "Not enough quarters of history in the filings for the model.",
            case_id=case_id,
            case_note=case_note,
        )
        (out / f"{item.cik}.json").write_text(
            record.model_dump_json(), encoding="utf-8", newline="\n"
        )
        rows.append(
            RealCompanyRow(
                company_id=dossier.company.company_id,
                cik=item.cik,
                name=item.name,
                ticker=item.tickers[0].upper() if item.tickers else None,
                sector=dossier.company.sector,
                country=dossier.company.country,
                evidence=evidence,
                support_status=dossier.support_status,
                revenue_quarters=next(
                    (c.quarters_valid for c in dossier.coverage if c.metric == "revenue"), 0
                ),
                has_forecast=live is not None,
                has_case=case_id is not None,
            )
        )
        if progress is not None:
            progress(number, len(universe.companies))
    index = RealIndex(
        universe_id=universe.universe_id,
        as_of=as_of,
        forecast_id=forecast.forecast_id,
        companies=tuple(rows),
    )
    (out / "index.json").write_text(index.model_dump_json(), encoding="utf-8", newline="\n")
    return index
