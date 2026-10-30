"""XBRL normalization on synthetic facts: one scenario per rule of Stage 11.

Every company, accession and value here is invented; the facts have the shape of SEC
Company Facts so the same code runs on the archived sample.
"""

import json
import os
import shutil
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.metrics import LineageMethod
from multiverse_contracts.normalized import (
    FiscalPeriod,
    NormalizedValue,
    QualityFlag,
)
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.models import RawObject
from multiverse_pipelines.xbrl import cli
from multiverse_pipelines.xbrl.calendar import FiscalCalendar
from multiverse_pipelines.xbrl.facts import Fact, facts_from_companyfacts, observe
from multiverse_pipelines.xbrl.normalize import CompanyNormalizer, rounding, scale_mismatch
from multiverse_pipelines.xbrl.tables import coverage, read_jsonl, write_outputs

CIK = "0000000001"
Q1, Q2, Q3, Q4, FY = FiscalPeriod
A1, A2, A3 = "0000000001-24-000001", "0000000001-24-000002", "0000000001-24-000003"
K1, KA, K2 = "0000000001-25-000001", "0000000001-25-000002", "0000000001-26-000001"
FILED = {
    A1: ("2024-04-25", "10-Q"),
    A2: ("2024-07-25", "10-Q"),
    A3: ("2024-10-25", "10-Q"),
    K1: ("2025-02-14", "10-K"),
    KA: ("2025-03-10", "10-K/A"),
    K2: ("2026-02-13", "10-K"),
}
PERIODS = {
    "Q1": ("2024-01-01", "2024-03-31"),
    "Q2": ("2024-04-01", "2024-06-30"),
    "Q3": ("2024-07-01", "2024-09-30"),
    "H1": ("2024-01-01", "2024-06-30"),
    "9M": ("2024-01-01", "2024-09-30"),
    "FY": ("2024-01-01", "2024-12-31"),
    "FY23": ("2023-01-01", "2023-12-31"),
    "9M23": ("2023-01-01", "2023-09-30"),
}


def f(
    tag: str,
    value: int | str,
    period: str,
    accession: str,
    *,
    unit: str = "USD",
    taxonomy: str = "us-gaap",
) -> Fact:
    filed, form = FILED[accession]
    if period.startswith("@"):
        start, end = None, date.fromisoformat(period[1:])
    else:
        first, last = PERIODS[period]
        start, end = date.fromisoformat(first), date.fromisoformat(last)
    fy = 2024 if accession in (K1, KA) else 2025 if accession == K2 else None
    return Fact(
        f"{taxonomy}:{tag}",
        unit,
        start,
        end,
        Decimal(str(value)),
        accession,
        form,
        date.fromisoformat(filed),
        fy,
    )


def company() -> list[Fact]:
    """Calendar-year filer: three 10-Qs, a 10-K, an amendment and next year's 10-K."""
    return [
        # Income statement: quarters reported, plus year-to-date totals.
        f("Revenues", 100, "Q1", A1),
        f("Revenues", 110, "Q2", A2),
        f("Revenues", 210, "H1", A2),
        f("Revenues", 120, "Q3", A3),
        f("Revenues", 330, "9M", A3),
        f("Revenues", 460, "FY", K1),
        f("Revenues", 400, "FY23", K1),
        f("Revenues", 455, "FY", K2),  # restated in the next 10-K
        f("RevenueFromContractWithCustomerExcludingAssessedTax", 100, "Q1", A1),
        f("RevenueFromContractWithCustomerExcludingAssessedTax", 90, "Q2", A2),
        f("ResearchAndDevelopmentExpense", -5, "Q1", A1),
        # Cash flow: year-to-date only.
        f("NetCashProvidedByUsedInOperatingActivities", 30, "Q1", A1),
        f("NetCashProvidedByUsedInOperatingActivities", 70, "H1", A2),
        f("NetCashProvidedByUsedInOperatingActivities", 100, "9M", A3),
        f("NetCashProvidedByUsedInOperatingActivities", 150, "FY", K1),
        f("NetCashProvidedByUsedInOperatingActivities", 152, "FY", KA),
        f("PaymentsToAcquirePropertyPlantAndEquipment", 10, "Q1", A1),
        f("PaymentsToAcquirePropertyPlantAndEquipment", 25, "H1", A2),
        f("PaymentsToAcquirePropertyPlantAndEquipment", 45, "9M", A3),
        f("PaymentsToAcquirePropertyPlantAndEquipment", 60, "FY", K1),
        # Balance sheet: instants at quarter ends, and last year's end as a comparative.
        f("CashAndCashEquivalentsAtCarryingValue", 45, "@2023-12-31", A1),
        f("CashAndCashEquivalentsAtCarryingValue", 50, "@2024-03-31", A1),
        f("CashAndCashEquivalentsAtCarryingValue", 55, "@2024-06-30", A2),
        f("CashAndCashEquivalentsAtCarryingValue", 60, "@2024-09-30", A3),
        f("CashAndCashEquivalentsAtCarryingValue", 65, "@2024-12-31", K1),
        # An average: never subtracted.
        f("WeightedAverageNumberOfDilutedSharesOutstanding", 10, "Q1", A1, unit="shares"),
        f("WeightedAverageNumberOfDilutedSharesOutstanding", 11, "Q2", A2, unit="shares"),
        f("WeightedAverageNumberOfDilutedSharesOutstanding", 12, "Q3", A3, unit="shares"),
        f("WeightedAverageNumberOfDilutedSharesOutstanding", 11, "FY", K1, unit="shares"),
    ]


def rows_of(facts: list[Fact], cik: str = CIK) -> dict[tuple[str, int, str, str], NormalizedValue]:
    return {
        (r.metric, r.fiscal_year, r.fiscal_period.value, r.revision.value): r
        for r in CompanyNormalizer(cik, facts).normalize()
    }


@pytest.fixture(scope="module")
def table() -> dict[tuple[str, int, str, str], NormalizedValue]:
    return rows_of(company())


def get(
    table: dict[tuple[str, int, str, str], NormalizedValue],
    metric: str,
    period: FiscalPeriod,
    revision: str = "original",
    year: int = 2024,
) -> NormalizedValue:
    return table[(metric, year, period.value, revision)]


# ---------------------------------------------------------------- quarters


def test_reported_quarters_and_q4_as_year_minus_nine_months(table: dict) -> None:
    values = [get(table, "revenue", p).value for p in (Q1, Q2, Q3, Q4, FY)]
    assert values == ["100", "110", "120", "130", "460"]
    q4 = get(table, "revenue", Q4)
    assert q4.method is LineageMethod.FY_MINUS_NINE_MONTHS
    assert [(s.value, s.sign, s.accession) for s in q4.sources] == [("460", 1, K1), ("330", -1, A3)]
    assert (q4.accession, q4.filed) == (K1, date(2025, 2, 14))  # known once the 10-K is filed
    assert (q4.period_start, q4.period_end) == (date(2024, 10, 1), date(2024, 12, 31))


def test_q4_is_never_the_annual_total(table: dict) -> None:
    assert get(table, "revenue", Q4).value != get(table, "revenue", FY).value
    assert get(table, "revenue", FY).method is LineageMethod.REPORTED


def test_cash_flow_quarters_come_from_year_to_date_differences(table: dict) -> None:
    cfo = [get(table, "cfo", p) for p in (Q1, Q2, Q3, Q4)]
    assert [r.value for r in cfo] == ["30", "40", "30", "50"]
    assert [r.method for r in cfo] == [
        LineageMethod.REPORTED,
        LineageMethod.YTD_TO_QUARTER,
        LineageMethod.YTD_TO_QUARTER,
        LineageMethod.FY_MINUS_NINE_MONTHS,
    ]
    assert cfo[1].filed == date(2024, 7, 25)


def test_q4_from_three_reported_quarters_when_nine_months_is_missing() -> None:
    facts = [
        f("OperatingIncomeLoss", 10, "Q1", A1),
        f("OperatingIncomeLoss", 11, "Q2", A2),
        f("OperatingIncomeLoss", 12, "Q3", A3),
        f("OperatingIncomeLoss", 50, "FY", K1),
    ]
    q4 = rows_of(facts)[("operating_income", 2024, "Q4", "original")]
    assert (q4.value, q4.method) == ("17", LineageMethod.FY_MINUS_THREE_QUARTERS)
    assert len(q4.sources) == 4


def test_an_average_is_never_subtracted(table: dict) -> None:
    q4 = get(table, "shares_diluted", Q4)
    assert q4.value is None
    assert "average" in (q4.missing_reason or "")
    assert get(table, "shares_diluted", Q3).value == "12"


def test_instant_values_are_taken_at_quarter_ends_and_never_derived(table: dict) -> None:
    cash = [get(table, "cash", p) for p in (Q1, Q2, Q3, Q4)]
    assert [r.value for r in cash] == ["50", "55", "60", "65"]
    assert all(r.method is LineageMethod.REPORTED and r.period_start is None for r in cash)
    assert get(table, "cash", Q4, year=2023).value == "45"  # last year's end, from a comparative
    assert ("cash", 2024, "FY", "original") not in table


def test_missing_is_never_zero(table: dict) -> None:
    cogs = get(table, "cogs", Q1)
    assert cogs.value is None
    assert cogs.missing_reason
    assert cogs.sources == ()


# ---------------------------------------------------------------- revisions


def test_a_restatement_keeps_both_values(table: dict) -> None:
    original, latest = get(table, "revenue", FY), get(table, "revenue", FY, "latest")
    assert (original.value, latest.value) == ("460", "455")
    assert QualityFlag.RESTATED in latest.flags
    assert latest.original_value == "460"
    assert (latest.accession, latest.filed) == (K2, date(2026, 2, 13))
    assert QualityFlag.RESTATED not in original.flags
    assert get(table, "revenue", Q4, "latest").value == "125"  # derived from the restated year


def test_an_amendment_is_the_latest_value_and_flagged(table: dict) -> None:
    latest = get(table, "cfo", FY, "latest")
    assert latest.value == "152"
    assert {QualityFlag.FROM_AMENDMENT, QualityFlag.RESTATED} <= set(latest.flags)
    assert get(table, "cfo", FY).value == "150"


def test_duplicates_are_dropped_and_conflicts_withheld() -> None:
    facts = [
        f("Revenues", 100, "Q1", A1),
        f("Revenues", 100, "Q1", A1),
        f("Revenues", 110, "Q2", A2),
        f("Revenues", 111, "Q2", A2),
        f("Revenues", 460, "FY", K1),
    ]
    assert observe(facts)[1] == 1
    q2 = rows_of(facts)[("revenue", 2024, "Q2", "original")]
    assert q2.value is None
    assert q2.quality is QualitySeverity.BLOCKING
    assert QualityFlag.CONFLICT_IN_FILING in q2.flags
    assert A2 in (q2.missing_reason or "")


# ---------------------------------------------------------------- concepts


def test_overlapping_concepts_keep_reconciliation_evidence(table: dict) -> None:
    q1, q2 = get(table, "revenue", Q1), get(table, "revenue", Q2)
    assert q1.concept == "us-gaap:Revenues"
    [evidence] = q1.alternatives
    assert evidence.concept == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    assert (evidence.value, evidence.difference) == ("100", "0")
    assert QualityFlag.CONCEPT_DISAGREEMENT not in q1.flags
    assert q2.alternatives[0].difference == "20"
    assert QualityFlag.CONCEPT_DISAGREEMENT in q2.flags


def test_one_concept_per_year_and_no_derivation_across_concepts() -> None:
    facts = [
        f("SalesRevenueNet", 290, "9M23", K1),
        f("SalesRevenueNet", 400, "FY23", K1),
        f("Revenues", 460, "FY", K1),
        f("SalesRevenueNet", 330, "9M", A3),
    ]
    rows = rows_of(facts)
    assert rows[("revenue", 2023, "Q4", "original")].value == "110"
    assert rows[("revenue", 2023, "FY", "original")].concept == "us-gaap:SalesRevenueNet"
    assert rows[("revenue", 2024, "FY", "original")].concept == "us-gaap:Revenues"
    q4 = rows[("revenue", 2024, "Q4", "original")]
    assert q4.value is None  # FY in Revenues and 9M in SalesRevenueNet are not combined
    assert "Q4 needs" in (q4.missing_reason or "")


def test_a_fallback_or_broader_concept_is_flagged() -> None:
    facts = [
        f("PaymentsToAcquirePropertyPlantAndEquipment", 60, "FY", K1),
        f("PaymentsToAcquireProductiveAssets", 12, "Q1", A1),
        f("ProfitLoss", 9, "Q1", A1),
    ]
    rows = rows_of(facts)
    capex = rows[("capex", 2024, "Q1", "original")]
    assert capex.concept == "us-gaap:PaymentsToAcquireProductiveAssets"
    assert {QualityFlag.CONCEPT_FALLBACK, QualityFlag.BROADER_CONCEPT} <= set(capex.flags)
    income = rows[("net_income", 2024, "Q1", "original")]
    assert QualityFlag.INCLUDES_NONCONTROLLING in income.flags


def test_a_negative_expense_is_kept_and_flagged(table: dict) -> None:
    rnd = get(table, "rnd", Q1)
    assert rnd.value == "-5"
    assert QualityFlag.NEGATIVE_EXPENSE in rnd.flags


def test_a_negative_derived_quarter_is_flagged() -> None:
    facts = [
        f("PaymentsToAcquirePropertyPlantAndEquipment", 30, "Q1", A1),
        f("PaymentsToAcquirePropertyPlantAndEquipment", 25, "H1", A2),
        f("PaymentsToAcquirePropertyPlantAndEquipment", 80, "FY", K1),
    ]
    q2 = rows_of(facts)[("capex", 2024, "Q2", "original")]
    assert q2.value == "-5"
    assert QualityFlag.NEGATIVE_DERIVED in q2.flags


# ---------------------------------------------------------------- units and calendars


def test_a_foreign_currency_is_kept_without_conversion() -> None:
    facts = [
        f("Revenues", 100, "Q1", A1, unit="EUR"),
        f("Revenues", 460, "FY", K1, unit="EUR"),
        f("Revenues", 999, "Q1", A1, unit="USD/shares"),
    ]
    q1 = rows_of(facts)[("revenue", 2024, "Q1", "original")]
    assert (q1.value, q1.currency, q1.unit) == ("100", "EUR", "EUR")
    assert QualityFlag.NON_USD in q1.flags


def test_a_fifty_three_week_year_is_mapped_and_flagged() -> None:
    def g(value: int, start: str, end: str, accession: str, fy: int | None = None) -> Fact:
        filed, form = FILED[accession]
        return Fact(
            "us-gaap:Revenues",
            "USD",
            date.fromisoformat(start),
            date.fromisoformat(end),
            Decimal(value),
            accession,
            form,
            date.fromisoformat(filed),
            fy,
        )

    facts = [
        g(400, "2023-01-01", "2023-12-30", K1, 2024),  # 52 weeks, comparative
        g(100, "2023-12-31", "2024-03-30", A1),
        g(210, "2023-12-31", "2024-06-29", A2),
        g(330, "2023-12-31", "2024-09-28", A3),
        g(470, "2023-12-31", "2025-01-04", K1, 2024),  # 53 weeks: 371 days
    ]
    calendar = FiscalCalendar.from_facts(facts)
    year = calendar.year(2024)
    assert year is not None
    assert (year.length, year.fifty_three_weeks) == (371, True)
    assert year.quarter_ends[:3] == (date(2024, 3, 30), date(2024, 6, 29), date(2024, 9, 28))
    rows = rows_of(facts)
    q4, fy = rows[("revenue", 2024, "Q4", "original")], rows[("revenue", 2024, "FY", "original")]
    assert q4.value == "140"
    assert (q4.period_end - q4.period_start).days + 1 == 98  # a 14-week quarter
    assert QualityFlag.FIFTY_THREE_WEEKS in q4.flags
    assert QualityFlag.FIFTY_THREE_WEEKS in fy.flags
    assert QualityFlag.FIFTY_THREE_WEEKS not in rows[("revenue", 2024, "Q2", "original")].flags


def test_fiscal_years_take_the_label_their_10k_gives_them() -> None:
    facts = [
        Fact(
            "us-gaap:Revenues",
            "USD",
            date(2024, 2, 1),
            date(2025, 1, 31),
            Decimal(1),
            K1,
            "10-K",
            date(2025, 3, 20),
            2024,
        ),
    ]
    assert [y.label for y in FiscalCalendar.from_facts(facts).years] == [2024]


def test_a_mistyped_fiscal_year_label_falls_back_to_the_year_end() -> None:
    # A real 10-K (Interpublic, filed 2016-02-22) gives every fact of fiscal 2015 fy 1215.
    fact = Fact(
        "us-gaap:Revenues",
        "USD",
        date(2015, 1, 1),
        date(2015, 12, 31),
        Decimal(1),
        K1,
        "10-K",
        date(2016, 2, 22),
        1215,
    )
    assert [y.label for y in FiscalCalendar.from_facts([fact]).years] == [2015]


def test_scale_and_rounding_checks() -> None:
    assert scale_mismatch("1196", "1196000000")
    assert scale_mismatch("378", "378600000")
    assert not scale_mismatch("455", "460")
    assert (rounding(Decimal(4069000000)), rounding(Decimal(1234)), rounding(Decimal(0))) == (
        6,
        0,
        0,
    )


# ---------------------------------------------------------------- calculated values


def test_free_cash_flow_and_ebitda_show_their_formula(table: dict) -> None:
    fcf = get(table, "free_cash_flow", Q2)
    assert (fcf.value, fcf.method, fcf.formula) == ("25", LineageMethod.CALCULATED, "cfo - capex")
    assert sum(Decimal(s.value) * s.sign for s in fcf.sources) == Decimal(25)
    ebitda = get(table, "ebitda", Q1)
    assert ebitda.value is None
    assert ebitda.missing_reason == (
        "operating_income + depreciation_amortization: missing operating_income, "
        "depreciation_amortization"
    )


# ---------------------------------------------------------------- tables and CLI


def test_tables_round_trip_and_count_coverage(tmp_path: Path) -> None:
    rows = CompanyNormalizer(CIK, company()).normalize()
    counts = write_outputs(rows, tmp_path, inputs=[{"cik": CIK}], names={CIK: "Synthetic"})
    assert counts["rows"] == len(rows)
    assert read_jsonl(tmp_path / "values.jsonl") == rows
    header = (tmp_path / "values.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("cik,metric,fiscal_year,fiscal_period")
    schema = json.loads((tmp_path / "schema.json").read_text(encoding="utf-8"))
    assert schema["title"] == "NormalizedValue"
    revenue = coverage(rows)[CIK]["revenue"]
    assert revenue.valid[8] == 4  # 2024 Q1-Q4; 2023 has the year only
    assert "| Synthetic |" in (tmp_path / "coverage.md").read_text(encoding="utf-8")


def test_normalize_and_show_read_the_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in [n for n in os.environ if n.startswith("MULTIVERSE_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    archive = RawArchive(Path("var/raw"), budget_bytes=10_000_000)
    archive.tmp_dir.mkdir(parents=True)
    source = Path(__file__).parent / "fixtures" / "sec" / f"companyfacts-CIK{CIK}.json"
    shutil.copyfile(source, archive.tmp_dir / "facts.part")

    def describe(sha: str, size: int, path: str) -> RawObject:
        return RawObject(
            source_id="sec-edgar",
            dataset_id="sec-companyfacts",
            key=f"CIK{CIK}",
            cik=CIK,
            url="https://data.sec.gov/fixture",
            path=path,
            sha256=sha,
            size_bytes=size,
            file_format="json",
            content_encoding="identity",
            http_status=200,
            downloaded_at=datetime(2026, 10, 29, tzinfo=UTC),
            run_id="fixture",
            licence="fixture",
            terms_checked_on=date(2026, 10, 29),
            catalog_version="0.8.0",
        )

    archive.store(
        archive.tmp_dir / "facts.part",
        dataset_id="sec-companyfacts",
        key=f"CIK{CIK}",
        file_format="json",
        describe=describe,
    )
    assert cli.main(["normalize", "--cik", "1"]) == 0
    assert Path("var/data/normalized/sec/values.jsonl").exists()
    assert cli.main(["show", "--cik", "1", "--fiscal-year", "2024"]) == 0
    out = capsys.readouterr().out
    assert "| revenue | - | - | - | - | 0.0 R |" in out
    assert cli.main(["show", "--cik", "2", "--fiscal-year", "2024"]) == 2


def test_the_archived_fixture_parses_into_facts() -> None:
    doc = json.loads(
        (Path(__file__).parent / "fixtures" / "sec" / f"companyfacts-CIK{CIK}.json").read_text(
            encoding="utf-8"
        )
    )
    facts = facts_from_companyfacts(doc)
    assert len(facts) == 4
    assert {fact.concept for fact in facts} >= {"dei:EntityCommonStockSharesOutstanding"}
