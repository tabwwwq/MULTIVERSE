"""Synthetic demo dossiers of fictional companies (Stage 04, decision D-01).

Every name, ticker, CIK, accession number and figure in this module is invented.
CIKs use the 0099xxxxxx range, far above any CIK the SEC has assigned, and
synthetic filings never carry a link. Records are built through the contract
models, so they obey every rule the API will enforce.

Usage:
    uv run python -m multiverse_contracts.demo           # write fixtures/demo/companies.json
    uv run python -m multiverse_contracts.demo --check   # exit 1 if the file is stale
"""

import argparse
import json
import random
import sys
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from multiverse_contracts.companies import (
    AccountingStandard,
    Company,
    CompanyDossier,
    CompanyStatus,
    CoverageEntry,
    DataQualityFlag,
    FilingForm,
    FilingReference,
    QualitySeverity,
    Sector,
    SupportStatus,
)
from multiverse_contracts.metrics import Lineage, LineageMethod, MetricValue, Period, PeriodType
from multiverse_contracts.primitives import DataOrigin, MeasureUnit, Quantity, ValueKind

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "demo" / "companies.json"
AS_OF = datetime(2023, 3, 31, tzinfo=UTC)
SYNTHETIC = DataOrigin.SYNTHETIC
METRICS = ("revenue", "ebitda_calculated", "fcf_simple", "net_debt", "rnd_expense")


@dataclass(frozen=True)
class Quarter:
    fiscal_year: int
    fiscal_quarter: int
    end: date


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _last_saturday(year: int, month: int) -> date:
    end = _month_end(year, month)
    return end - timedelta(days=(end.weekday() - 5) % 7)


def fiscal_quarters(
    fy_end_month: int, first: tuple[int, int], last: tuple[int, int], week_based: bool = False
) -> tuple[Quarter, ...]:
    """Fiscal quarters from ``first`` to ``last`` (fiscal year, quarter), both included."""
    quarters = []
    year, quarter = first
    while (year, quarter) <= last:
        month, calendar_year = fy_end_month - 3 * (4 - quarter), year
        while month <= 0:
            month += 12
            calendar_year -= 1
        end = (
            _last_saturday(calendar_year, month) if week_based else _month_end(calendar_year, month)
        )
        quarters.append(Quarter(year, quarter, end))
        year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
    return tuple(quarters)


@dataclass(frozen=True)
class Spec:
    """Recipe for one fictional company."""

    slug: str
    company: Company
    quarters: tuple[Quarter, ...]
    base_revenue: float
    growth: float
    ebitda_margin: float
    fcf_margin: float
    net_debt_start: float
    rnd_share: float | None
    support_status: SupportStatus = SupportStatus.SUPPORTED
    support_reason: str | None = None
    missing: dict[tuple[str, int, int], str] = field(default_factory=dict)
    flags: tuple[DataQualityFlag, ...] = ()
    annual_filings: tuple[tuple[int, date, date], ...] = ()


def _usd(amount: float) -> Quantity:
    rounded = round(amount / 100_000) * 100_000
    return Quantity(value=str(rounded), unit=MeasureUnit.CURRENCY, currency="USD")


def _lineage(metric: str, quarter: int) -> Lineage:
    q4 = quarter == 4
    flow_method = LineageMethod.FY_MINUS_NINE_MONTHS if q4 else LineageMethod.REPORTED
    if metric == "revenue":
        return Lineage(concepts=("us-gaap:Revenues",), method=flow_method)
    if metric == "rnd_expense":
        return Lineage(concepts=("us-gaap:ResearchAndDevelopmentExpense",), method=flow_method)
    if metric == "ebitda_calculated":
        suffix = "; Q4 is the fiscal year minus nine months" if q4 else ""
        return Lineage(
            concepts=(
                "us-gaap:OperatingIncomeLoss",
                "us-gaap:DepreciationDepletionAndAmortization",
            ),
            method=LineageMethod.CALCULATED,
            formula=f"Operating income + depreciation and amortization{suffix}",
        )
    if metric == "fcf_simple":
        if quarter == 1:
            detail = ""
        elif q4:
            detail = "; Q4 is the fiscal year minus nine months"
        else:
            detail = "; cash flows are year-to-date in the filing, so prior quarters are subtracted"
        return Lineage(
            concepts=(
                "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
            ),
            method=LineageMethod.CALCULATED,
            formula=f"Operating cash flow − capital expenditure{detail}",
        )
    return Lineage(
        concepts=(
            "us-gaap:LongTermDebt",
            "us-gaap:ShortTermBorrowings",
            "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        ),
        method=LineageMethod.CALCULATED,
        formula="Long-term debt + short-term borrowings − cash and cash equivalents at period end",
    )


def _filed_at(day: date) -> datetime:
    return datetime.combine(day, time(21, 30), tzinfo=UTC)


def build_dossier(spec: Spec) -> CompanyDossier:
    rng = random.Random(spec.slug)
    cik = spec.company.cik or "0000000000"
    filings: list[FilingReference] = []
    values: list[MetricValue] = []
    net_debt = spec.net_debt_start
    season = (0.97, 1.0, 0.99, 1.05)

    for index, quarter in enumerate(spec.quarters):
        annual = quarter.fiscal_quarter == 4
        filed = quarter.end + timedelta(days=(58 if annual else 38) + rng.randint(0, 6))
        filing = FilingReference(
            filing_id=f"{spec.slug}-{quarter.fiscal_year}q{quarter.fiscal_quarter}",
            form=FilingForm.FORM_10K if annual else FilingForm.FORM_10Q,
            accession_number=f"{cik}-{filed.year % 100:02d}-{index + 1:06d}",
            period_end=quarter.end,
            filed_at=_filed_at(filed),
            data_origin=SYNTHETIC,
        )
        filings.append(filing)

        revenue = (
            spec.base_revenue
            * (1 + spec.growth) ** index
            * season[quarter.fiscal_quarter - 1]
            * (1 + rng.uniform(-0.02, 0.02))
        )
        fcf = revenue * (spec.fcf_margin + rng.uniform(-0.04, 0.04))
        net_debt -= fcf * 0.6
        amounts: dict[str, float | None] = {
            "revenue": revenue,
            "ebitda_calculated": revenue * (spec.ebitda_margin + rng.uniform(-0.015, 0.015)),
            "fcf_simple": fcf,
            "net_debt": net_debt,
            "rnd_expense": None
            if spec.rnd_share is None
            else revenue * spec.rnd_share * (1 + rng.uniform(-0.05, 0.05)),
        }

        for metric in METRICS:
            if metric == "net_debt":
                period = Period(type=PeriodType.INSTANT, end_date=quarter.end)
            else:
                period = Period(
                    type=PeriodType.FISCAL_QUARTER,
                    end_date=quarter.end,
                    fiscal_year=quarter.fiscal_year,
                    fiscal_quarter=quarter.fiscal_quarter,
                )
            key = (metric, quarter.fiscal_year, quarter.fiscal_quarter)
            reason = spec.missing.get(key) or spec.missing.get((metric, 0, 0))
            amount = amounts[metric]
            if amount is None and reason is None:
                reason = "The company does not report this item."
            values.append(
                MetricValue(
                    metric=metric,
                    quantity=None if reason else _usd(amount or 0.0),
                    missing_reason=reason,
                    kind=ValueKind.OBSERVED,
                    data_origin=SYNTHETIC,
                    period=period,
                    as_of=AS_OF,
                    source_ids=(filing.filing_id,),
                    lineage=None if reason else _lineage(metric, quarter.fiscal_quarter),
                )
            )

    for year, period_end, filed in spec.annual_filings:
        filings.append(
            FilingReference(
                filing_id=f"{spec.slug}-{year}-annual",
                form=FilingForm.FORM_20F,
                accession_number=f"{cik}-{filed.year % 100:02d}-{len(filings) + 1:06d}",
                period_end=period_end,
                filed_at=_filed_at(filed),
                data_origin=SYNTHETIC,
            )
        )

    coverage = tuple(
        CoverageEntry(
            metric=metric,
            quarters_valid=sum(1 for v in values if v.metric == metric and v.quantity is not None),
            quarters_expected=len(spec.quarters),
        )
        for metric in METRICS
        if spec.quarters
    )
    return CompanyDossier(
        company=spec.company,
        support_status=spec.support_status,
        support_reason=spec.support_reason,
        as_of=AS_OF,
        filings=tuple(filings),
        values=tuple(values),
        coverage=coverage,
        quality_flags=spec.flags,
    )


def _company(**fields: object) -> Company:
    # Validated from JSON, exactly as the API will receive it (strict mode, ISO dates).
    return Company.model_validate_json(json.dumps({"data_origin": SYNTHETIC, **fields}))


def demo_specs() -> tuple[Spec, ...]:
    currency_note = (
        "Reported in CAD until the end of FY2020. Values before the switch to USD are not "
        "converted; currency conversion with historical rates arrives in Stage 13."
    )
    return (
        Spec(
            slug="nwsc",
            company=_company(
                company_id="5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13",
                cik="0099000101",
                names=[
                    {
                        "name": "Northwind Microdevices Inc.",
                        "valid_from": "2012-03-01",
                        "valid_to": "2019-06-30",
                    },
                    {"name": "Northwind Semiconductors Inc.", "valid_from": "2019-07-01"},
                ],
                listings=[
                    {
                        "ticker": "NWMD",
                        "exchange": "NASDAQ",
                        "valid_from": "2012-03-01",
                        "valid_to": "2019-06-30",
                    },
                    {"ticker": "NWSC", "exchange": "NASDAQ", "valid_from": "2019-07-01"},
                ],
                sector=Sector.SEMICONDUCTORS,
                country="US",
                reporting_currency="USD",
                accounting_standard=AccountingStandard.US_GAAP,
                fiscal_year_end="12-31",
            ),
            quarters=fiscal_quarters(12, (2020, 1), (2022, 4)),
            base_revenue=1_150_000_000,
            growth=0.015,
            ebitda_margin=0.23,
            fcf_margin=0.11,
            net_debt_start=820_000_000,
            rnd_share=0.18,
            missing={
                ("rnd_expense", 2021, 3): (
                    "R&D expense is not tagged separately in this filing; it is included in "
                    "operating expenses."
                )
            },
            flags=(
                DataQualityFlag(
                    code="rnd_missing_quarter",
                    severity=QualitySeverity.WARNING,
                    message=(
                        "R&D expense is missing for FY2021 Q3. It is shown as missing, not as zero."
                    ),
                    metric="rnd_expense",
                ),
            ),
        ),
        Spec(
            slug="hlcn",
            company=_company(
                company_id="a7c2e9d4-1f3b-4c8a-b5e6-0d9f2a7c3e18",
                cik="0099000102",
                names=[{"name": "Halcyon Software Corp.", "valid_from": "2015-05-12"}],
                listings=[{"ticker": "HLCN", "exchange": "NYSE", "valid_from": "2015-05-12"}],
                sector=Sector.SOFTWARE,
                country="US",
                reporting_currency="USD",
                accounting_standard=AccountingStandard.US_GAAP,
                fiscal_year_end="06-30",
            ),
            quarters=fiscal_quarters(6, (2021, 1), (2023, 2)),
            base_revenue=640_000_000,
            growth=0.022,
            ebitda_margin=0.31,
            fcf_margin=0.26,
            net_debt_start=-450_000_000,
            rnd_share=0.24,
            flags=(
                DataQualityFlag(
                    code="non_calendar_fiscal_year",
                    severity=QualitySeverity.INFO,
                    message=(
                        "The fiscal year ends on 30 June, so fiscal quarters do not line up "
                        "with calendar quarters."
                    ),
                ),
            ),
        ),
        Spec(
            slug="mrdn",
            company=_company(
                company_id="3e8d1a6f-c4b2-4f97-8a1d-6b5c0e2f9a74",
                cik="0099000103",
                names=[{"name": "Meridian Health Devices Inc.", "valid_from": "2010-08-16"}],
                listings=[{"ticker": "MRDN", "exchange": "NASDAQ", "valid_from": "2010-08-16"}],
                sector=Sector.MEDICAL_DEVICES,
                country="US",
                reporting_currency="USD",
                accounting_standard=AccountingStandard.US_GAAP,
                fiscal_year_end="12-31",
                fiscal_52_53_week=True,
            ),
            quarters=fiscal_quarters(12, (2020, 1), (2022, 4), week_based=True),
            base_revenue=420_000_000,
            growth=0.01,
            ebitda_margin=0.19,
            fcf_margin=0.09,
            net_debt_start=310_000_000,
            rnd_share=0.07,
            missing={
                ("fcf_simple", 2021, 2): (
                    "CAPEX is not reported separately in this filing, so FCF (operating cash flow "
                    "− CAPEX) cannot be calculated."
                ),
                ("fcf_simple", 2021, 3): (
                    "CAPEX is not reported separately in this filing, so FCF (operating cash flow "
                    "− CAPEX) cannot be calculated."
                ),
            },
            flags=(
                DataQualityFlag(
                    code="capex_not_separated",
                    severity=QualitySeverity.WARNING,
                    message=(
                        "FCF is missing for FY2021 Q2 and Q3 because CAPEX was not reported "
                        "separately."
                    ),
                    metric="fcf_simple",
                ),
                DataQualityFlag(
                    code="fiscal_52_53_week",
                    severity=QualitySeverity.INFO,
                    message=(
                        "Quarters end on the last Saturday of the quarter's final month "
                        "(52/53-week "
                        "fiscal year), so period end dates move from year to year."
                    ),
                ),
            ),
        ),
        Spec(
            slug="agru",
            company=_company(
                company_id="c91f5b37-2d6e-4a08-93bc-71e4d0a8f562",
                cik="0099000104",
                names=[
                    {
                        "name": "Aurora Grid Utilities Corp.",
                        "valid_from": "2008-11-03",
                        "valid_to": "2021-09-30",
                    }
                ],
                listings=[
                    {
                        "ticker": "AGRU",
                        "exchange": "NYSE",
                        "valid_from": "2008-11-03",
                        "valid_to": "2021-09-30",
                    }
                ],
                sector=Sector.UTILITIES,
                country="US",
                reporting_currency="USD",
                accounting_standard=AccountingStandard.US_GAAP,
                fiscal_year_end="12-31",
                status=CompanyStatus.ACQUIRED,
                status_date="2021-09-30",
                status_note="Acquired by a fictional buyer. No filings after FY2021 Q2.",
            ),
            quarters=fiscal_quarters(12, (2019, 1), (2021, 2)),
            base_revenue=900_000_000,
            growth=0.004,
            ebitda_margin=0.36,
            fcf_margin=0.03,
            net_debt_start=4_200_000_000,
            rnd_share=None,
            missing={("rnd_expense", 0, 0): "The company does not report R&D expense."},
            flags=(
                DataQualityFlag(
                    code="left_the_market",
                    severity=QualitySeverity.INFO,
                    message=(
                        "Acquired on 2021-09-30. Its history stays in the data so that samples do "
                        "not suffer from survivorship bias."
                    ),
                ),
            ),
        ),
        Spec(
            slug="tslg",
            company=_company(
                company_id="0f6a2c8e-9b1d-4e53-a7c4-58d2e1b9f036",
                cik="0099000105",
                names=[{"name": "Tessaract Logistics Inc.", "valid_from": "2021-04-15"}],
                listings=[{"ticker": "TSLG", "exchange": "NASDAQ", "valid_from": "2021-04-15"}],
                sector=Sector.LOGISTICS,
                country="US",
                reporting_currency="USD",
                accounting_standard=AccountingStandard.US_GAAP,
                fiscal_year_end="12-31",
            ),
            quarters=fiscal_quarters(12, (2021, 2), (2022, 4)),
            base_revenue=210_000_000,
            growth=0.04,
            ebitda_margin=0.08,
            fcf_margin=-0.05,
            net_debt_start=150_000_000,
            rnd_share=0.02,
            support_status=SupportStatus.INSUFFICIENT_HISTORY,
            support_reason=(
                "7 of the 8 fiscal quarters needed for empirical forecasts. Only the demo mode is "
                "available for this company."
            ),
            flags=(
                DataQualityFlag(
                    code="short_history",
                    severity=QualitySeverity.WARNING,
                    message="Listed in April 2021: only 7 fiscal quarters of history so far.",
                ),
            ),
        ),
        Spec(
            slug="kstl",
            company=_company(
                company_id="e4b8d0a2-7c3f-4196-b2e5-9a0c6d1f8e47",
                cik="0099000106",
                names=[{"name": "Kestrel Instruments Ltd.", "valid_from": "2014-02-03"}],
                listings=[{"ticker": "KSTL", "exchange": "NASDAQ", "valid_from": "2014-02-03"}],
                sector=Sector.INSTRUMENTS,
                country="CA",
                reporting_currency="USD",
                accounting_standard=AccountingStandard.US_GAAP,
                fiscal_year_end="12-31",
            ),
            quarters=fiscal_quarters(12, (2020, 1), (2022, 4)),
            base_revenue=300_000_000,
            growth=0.012,
            ebitda_margin=0.21,
            fcf_margin=0.12,
            net_debt_start=95_000_000,
            rnd_share=0.11,
            missing={
                (metric, 2020, quarter): currency_note
                for metric in METRICS
                for quarter in (1, 2, 3, 4)
            },
            flags=(
                DataQualityFlag(
                    code="reporting_currency_change",
                    severity=QualitySeverity.WARNING,
                    message=(
                        "Reporting currency changed from CAD to USD at the start of FY2021. "
                        "Earlier "
                        "quarters are kept as missing rather than converted."
                    ),
                ),
            ),
        ),
        Spec(
            slug="vltx",
            company=_company(
                company_id="8d2c6e1a-4f9b-4b70-8e3d-c5a1f7b2e906",
                cik="0099000107",
                names=[{"name": "Valtrix AG", "valid_from": "2016-09-20"}],
                listings=[{"ticker": "VLTX", "exchange": "NYSE", "valid_from": "2016-09-20"}],
                sector=Sector.INDUSTRIAL_MACHINERY,
                country="DE",
                reporting_currency="EUR",
                accounting_standard=AccountingStandard.IFRS,
                fiscal_year_end="12-31",
            ),
            quarters=(),
            base_revenue=0,
            growth=0,
            ebitda_margin=0,
            fcf_margin=0,
            net_debt_start=0,
            rnd_share=None,
            support_status=SupportStatus.UNSUPPORTED,
            support_reason=(
                "Files annual reports on Form 20-F under IFRS in EUR. MULTIVERSE supports US-GAAP "
                "filers reporting in USD until currency and IFRS handling arrive "
                "(decisions D-02 and D-04)."
            ),
            flags=(
                DataQualityFlag(
                    code="unsupported_standard",
                    severity=QualitySeverity.BLOCKING,
                    message=(
                        "IFRS reports in EUR are not normalized yet, so no financial values "
                        "are shown."
                    ),
                ),
            ),
            annual_filings=(
                (2021, date(2021, 12, 31), date(2022, 4, 8)),
                (2022, date(2022, 12, 31), date(2023, 3, 24)),
            ),
        ),
    )


def build_all() -> tuple[CompanyDossier, ...]:
    return tuple(build_dossier(spec) for spec in demo_specs())


def render() -> str:
    records = [dossier.model_dump(mode="json") for dossier in build_all()]
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the fixture file is stale")
    args = parser.parse_args(argv)
    expected = render()
    if args.check:
        current = FIXTURE_PATH.read_text(encoding="utf-8") if FIXTURE_PATH.exists() else ""
        if current != expected:
            print(f"{FIXTURE_PATH.name} is stale. Run: npm run contracts:gen", file=sys.stderr)
            return 1
        print(f"{FIXTURE_PATH.name} is up to date ({len(build_all())} demo companies)")
        return 0
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
