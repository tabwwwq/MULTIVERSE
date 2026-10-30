"""Broken chronology alerts from a company's filing index and current values.

Fact-level alerts (estimates, filing date mismatches, filings missing from the index)
come with the history (``vintages.fact_alerts``). These look at the filings and at the
values known today:

- a periodic report public before the report of an earlier period;
- an amendment public before the report it amends;
- a filing accepted more than a day after its filing date;
- a report filed after the longest regular deadline;
- a Form 15 with no periodic report after it;
- four reported quarters that do not add up to the reported fiscal year.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from multiverse_contracts.companies import QualitySeverity
from multiverse_contracts.metrics import LineageMethod
from multiverse_contracts.normalized import FiscalPeriod, NormalizedValue, PeriodKind, Revision
from multiverse_contracts.pit import AlertKind, ChronologyAlert, PitValue
from multiverse_pipelines.pit.clock import eastern_date
from multiverse_pipelines.pit.filings import Filing, FilingIndex
from multiverse_pipelines.xbrl.concepts import METRICS

DEADLINE_DAYS = {"10-Q": 45, "10-K": 90}
SUM_TOLERANCE = Decimal("0.005")
ADDITIVE = frozenset(
    spec.metric for spec in METRICS if spec.additive and spec.kind is PeriodKind.DURATION
)


def _alert(
    kind: AlertKind, severity: QualitySeverity, cik: str, filing: Filing, detail: str
) -> ChronologyAlert:
    return ChronologyAlert(
        kind=kind,
        severity=severity,
        cik=cik,
        accession=filing.accession,
        period_end=filing.report_date,
        known_at=filing.known_at,
        detail=detail,
    )


def filing_alerts(
    cik: str, index: FilingIndex, fact_accessions: frozenset[str]
) -> list[ChronologyAlert]:
    alerts: list[ChronologyAlert] = []
    relevant = [f for f in index.filings if f.periodic or f.accession in fact_accessions]
    for filing in relevant:
        if filing.accepted is not None:
            late_by = (eastern_date(filing.accepted) - filing.filing_date).days
            if late_by > 1:
                alerts.append(
                    _alert(
                        AlertKind.ACCEPTED_AFTER_FILING_DATE,
                        QualitySeverity.WARNING,
                        cik,
                        filing,
                        f"{filing.form} dated {filing.filing_date} was accepted {late_by} days "
                        "later; it counts as public from its acceptance",
                    )
                )
    originals = [f for f in index.filings if f.periodic and not f.amended and f.report_date]
    first_by_period: dict[tuple[str, date], Filing] = {}
    for filing in originals:
        report = filing.report_date
        if report is None:
            continue
        first_by_period.setdefault((filing.base_form, report), filing)
        deadline = DEADLINE_DAYS.get(filing.base_form)
        if deadline and filing.filing_date > report + timedelta(days=deadline):
            days = (filing.filing_date - report).days
            alerts.append(
                _alert(
                    AlertKind.LATE_REPORT,
                    QualitySeverity.INFO,
                    cik,
                    filing,
                    f"{filing.form} for {report} filed {days} days after the "
                    f"period end (regular deadline at most {deadline})",
                )
            )
    latest_period = None
    for filing in sorted(originals, key=lambda f: (f.known_at, f.accession)):
        if filing.base_form not in ("10-Q", "10-K"):
            continue
        if latest_period is not None and filing.report_date and filing.report_date < latest_period:
            alerts.append(
                _alert(
                    AlertKind.REPORT_OUT_OF_ORDER,
                    QualitySeverity.WARNING,
                    cik,
                    filing,
                    f"{filing.form} for {filing.report_date} became public after a report "
                    f"for {latest_period}",
                )
            )
        if filing.report_date and (latest_period is None or filing.report_date > latest_period):
            latest_period = filing.report_date
    for filing in index.filings:
        if not (filing.periodic and filing.amended and filing.report_date):
            continue
        original = first_by_period.get((filing.base_form, filing.report_date))
        if original is not None and original.known_at > filing.known_at:
            alerts.append(
                _alert(
                    AlertKind.AMENDMENT_BEFORE_ORIGINAL,
                    QualitySeverity.WARNING,
                    cik,
                    filing,
                    f"{filing.form} for {filing.report_date} became public before the "
                    f"{original.form} it amends ({original.accession})",
                )
            )
    gone = index.deregistered(index.filings[-1].known_at) if index.filings else None
    if gone is not None:
        alerts.append(
            _alert(
                AlertKind.DEREGISTRATION,
                QualitySeverity.INFO,
                cik,
                gone,
                f"{gone.form} filed on {gone.filing_date} and no 10-Q or 10-K since: quarters "
                "after it are inactive, not missing",
            )
        )
    return alerts


def sum_alerts(cik: str, values: Sequence[PitValue]) -> list[ChronologyAlert]:
    """Reported quarters against the reported fiscal year, as known today."""
    current: dict[tuple[str, int], dict[FiscalPeriod, NormalizedValue]] = defaultdict(dict)
    for item in values:
        row = item.value
        if item.known_to is None and row.revision is Revision.LATEST and row.metric in ADDITIVE:
            current[(row.metric, row.fiscal_year)][row.fiscal_period] = row
    alerts: list[ChronologyAlert] = []
    for (metric, year), periods in sorted(current.items()):
        if len(periods) != 5:
            continue
        rows = list(periods.values())
        if any(r.value is None or r.method is not LineageMethod.REPORTED for r in rows):
            continue
        total = periods[FiscalPeriod.FY]
        quarters = sum(
            (Decimal(periods[p].value or "0") for p in periods if p is not FiscalPeriod.FY),
            Decimal(0),
        )
        annual = Decimal(total.value or "0")
        if abs(quarters - annual) > SUM_TOLERANCE * abs(annual):
            alerts.append(
                ChronologyAlert(
                    kind=AlertKind.QUARTERS_DO_NOT_SUM,
                    severity=QualitySeverity.WARNING,
                    cik=cik,
                    accession=total.accession,
                    metric=metric,
                    period_end=total.period_end,
                    detail=(
                        f"{metric} fiscal {year}: four reported quarters add up to {quarters}, "
                        f"the year is {annual}"
                    ),
                )
            )
    return alerts
