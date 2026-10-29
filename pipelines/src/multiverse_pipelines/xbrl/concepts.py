"""Concept map: which US-GAAP concepts may stand for each canonical metric, in what order.

Similar tags are not merged into one number. Each metric lists its candidates with their
relation to the metric: the primary concept, equivalents (another name for the same
total), narrower ones (a part of it) and broader ones (it plus something else). One
concept is chosen per company and fiscal year; another one is used for a period only as
a fallback, with a flag. Every other candidate reported for the same period is kept as
reconciliation evidence, and equivalents that disagree are flagged (docs/04).
"""

from dataclasses import dataclass
from typing import Literal

from multiverse_contracts.normalized import ConceptRelation, PeriodKind, QualityFlag

P, E, N, B = (
    ConceptRelation.PRIMARY,
    ConceptRelation.EQUIVALENT,
    ConceptRelation.NARROWER,
    ConceptRelation.BROADER,
)


@dataclass(frozen=True)
class Candidate:
    concept: str
    relation: ConceptRelation
    flag: QualityFlag | None = None


@dataclass(frozen=True)
class MetricSpec:
    metric: str
    label: str
    kind: PeriodKind
    unit: Literal["money", "shares"]
    candidates: tuple[Candidate, ...]
    additive: bool = True
    positive: bool = False
    note: str = ""


@dataclass(frozen=True)
class CalculatedSpec:
    metric: str
    label: str
    plus: tuple[str, ...]
    minus: tuple[str, ...]
    formula: str


def gaap(
    *items: tuple[str, ConceptRelation] | tuple[str, ConceptRelation, QualityFlag],
) -> tuple[Candidate, ...]:
    return tuple(Candidate(f"us-gaap:{item[0]}", *item[1:]) for item in items)


DURATION, INSTANT = PeriodKind.DURATION, PeriodKind.INSTANT

METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "revenue",
        "Revenue",
        DURATION,
        "money",
        gaap(
            ("Revenues", P),
            ("RevenueFromContractWithCustomerExcludingAssessedTax", E),
            ("RevenueFromContractWithCustomerIncludingAssessedTax", E),
            ("SalesRevenueNet", E),
        ),
        positive=True,
        note="Total revenue. Contract revenue (ASC 606) stands for it when no Revenues is filed.",
    ),
    MetricSpec(
        "cogs",
        "Cost of revenue",
        DURATION,
        "money",
        gaap(
            ("CostOfRevenue", P),
            ("CostOfGoodsAndServicesSold", E),
            ("CostOfGoodsSold", N),
        ),
        positive=True,
    ),
    MetricSpec(
        "operating_income",
        "Operating income",
        DURATION,
        "money",
        gaap(("OperatingIncomeLoss", P)),
        note="May be negative.",
    ),
    MetricSpec(
        "net_income",
        "Net income attributable to the parent",
        DURATION,
        "money",
        gaap(
            ("NetIncomeLoss", P),
            ("ProfitLoss", B, QualityFlag.INCLUDES_NONCONTROLLING),
        ),
        note="Not income available to common stockholders; ProfitLoss includes minorities.",
    ),
    MetricSpec(
        "rnd",
        "Research and development",
        DURATION,
        "money",
        gaap(
            ("ResearchAndDevelopmentExpense", P),
            ("ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost", N),
        ),
        positive=True,
        note="Only where tagged separately; many companies do not report it.",
    ),
    MetricSpec(
        "depreciation_amortization",
        "Depreciation and amortization",
        DURATION,
        "money",
        gaap(
            ("DepreciationDepletionAndAmortization", P),
            ("DepreciationAndAmortization", E),
            ("DepreciationAmortizationAndAccretionNet", B),
            ("Depreciation", N),
        ),
        positive=True,
        note="From the cash flow statement, year-to-date in 10-Q filings.",
    ),
    MetricSpec(
        "cfo",
        "Cash from operations",
        DURATION,
        "money",
        gaap(
            ("NetCashProvidedByUsedInOperatingActivities", P),
            ("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", N),
        ),
    ),
    MetricSpec(
        "capex",
        "Capital expenditure",
        DURATION,
        "money",
        gaap(
            ("PaymentsToAcquirePropertyPlantAndEquipment", P),
            ("PaymentsToAcquireProductiveAssets", B),
        ),
        positive=True,
        note="Payments for property, plant and equipment; acquisitions of businesses excluded.",
    ),
    MetricSpec(
        "cash",
        "Cash and cash equivalents",
        INSTANT,
        "money",
        gaap(
            ("CashAndCashEquivalentsAtCarryingValue", P),
            ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", B),
        ),
    ),
    MetricSpec(
        "long_term_debt",
        "Long-term debt, current maturities included",
        INSTANT,
        "money",
        gaap(
            ("LongTermDebt", P),
            ("LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", B),
        ),
    ),
    MetricSpec(
        "long_term_debt_noncurrent",
        "Long-term debt, non-current",
        INSTANT,
        "money",
        gaap(
            ("LongTermDebtNoncurrent", P),
            ("LongTermDebtAndCapitalLeaseObligations", B),
        ),
    ),
    MetricSpec(
        "debt_current",
        "Current maturities of long-term debt",
        INSTANT,
        "money",
        gaap(
            ("LongTermDebtCurrent", P),
            ("LongTermDebtAndCapitalLeaseObligationsCurrent", B),
            ("DebtCurrent", B),
        ),
    ),
    MetricSpec(
        "shares_diluted",
        "Weighted-average diluted shares",
        DURATION,
        "shares",
        gaap(("WeightedAverageNumberOfDilutedSharesOutstanding", P)),
        additive=False,
        note="An average, not a sum: quarters are never derived by subtraction.",
    ),
    MetricSpec(
        "shares_outstanding",
        "Common shares outstanding",
        INSTANT,
        "shares",
        gaap(("CommonStockSharesOutstanding", P)),
    ),
)

CALCULATED: tuple[CalculatedSpec, ...] = (
    CalculatedSpec(
        "free_cash_flow",
        "Free cash flow (unadjusted)",
        plus=("cfo",),
        minus=("capex",),
        formula="cfo - capex",
    ),
    CalculatedSpec(
        "ebitda",
        "EBITDA (operating income plus D&A, not adjusted)",
        plus=("operating_income", "depreciation_amortization"),
        minus=(),
        formula="operating_income + depreciation_amortization",
    ),
)

SPECS = {spec.metric: spec for spec in METRICS}
