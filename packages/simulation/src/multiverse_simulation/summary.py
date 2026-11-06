"""From paths to a report: quantiles, paired changes, risks, convergence and tails.

A paired change is computed path by path and only then summarized: the quantile of a difference
is not the difference of quantiles. Standard errors are Monte Carlo errors only. They say how far
a number is from what infinitely many paths of the same model would give, and nothing about
whether the model is right.
"""

import hashlib
import math
import uuid
from calendar import monthrange
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal

import numpy as np

from multiverse_contracts.decisions import DecisionModel, add_quarters
from multiverse_contracts.distributions import distribution_points
from multiverse_contracts.interventions import CATALOG
from multiverse_contracts.manifest import ReproducibilityManifest
from multiverse_contracts.primitives import (
    CausalStatus,
    DataOrigin,
    ResultMode,
    UncertaintyType,
)
from multiverse_contracts.results import (
    ChangeDistribution,
    ChangeUnit,
    HistogramBin,
    MetricResult,
    ObservedPoint,
    PairedChange,
    QuantilePoint,
    ResultMetric,
    ResultStatus,
    ScenarioResult,
    ScenarioRun,
    ScenarioSeries,
    TimelineEvent,
)
from multiverse_contracts.simulation import (
    CONDITIONAL_LABEL,
    CaseHistoryPoint,
    ConvergenceRow,
    RiskRow,
    SensitivityRow,
    SimulationCase,
    SimulationDiagnostics,
    SimulationManifest,
    SimulationReport,
    SimulationSettings,
    TailDriver,
    TailRow,
    ValueRow,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_finance import __version__ as finance_version
from multiverse_simulation import __version__ as simulation_version
from multiverse_simulation.run import ALTERNATE, BASELINE, METRICS, RISKS, Frame, generator
from multiverse_simulation.shocks import (
    SECTOR_GROWTH,
    SECTOR_MARGIN,
    Floats,
    ShockModel,
    block_indices,
)

CONVERGENCE_SIZES = (500, 1000, 3000, 10_000)
SECTIONS = 10
TAIL_ROWS = 10
BINS = 20
CORRELATION_DRAWS = 2000
TAIL_PATHS = 3000
"""Below this, a tail probability near 1% rests on a few dozen paths (docs/08)."""
RESULT_METRICS = {
    "revenue": (ResultMetric.REVENUE, "Revenue", "Revenue of the quarter on the path."),
    "ebitda": (ResultMetric.EBITDA, "EBITDA (calculated)", "EBIT + D&A, after one-off items."),
    "fcff": (
        ResultMetric.FCF,
        "FCFF (unlevered, model)",
        "EBIT − tax on EBIT + D&A − CAPEX − ΔNWC, with deals in their quarter.",
    ),
    "net_debt": (ResultMetric.NET_DEBT, "Net debt", "Debt and any shortfall, less cash."),
}
RISK_LABELS = {
    "funding_shortfall": "Funding shortfall: cash and the revolver do not cover needs",
    "covenant_breach": "Covenant breach in any quarter",
    "below_minimum_cash": "Cash below its minimum in any quarter",
    "negative_fcff_year": "Negative operating FCFF over four quarters in a row",
}
SCENARIOS = {BASELINE: "baseline", ALTERNATE: "alt_a"}


def money(value: float) -> str:
    return f"{value:.2f}"


def quarter_ends(as_of: date, quarters: int) -> tuple[date, ...]:
    ends = []
    for number in range(1, quarters + 1):
        day = add_quarters(as_of, number)
        ends.append(day.replace(day=monthrange(day.year, day.month)[1]))
    return tuple(ends)


def _label(day: date) -> str:
    return f"{day.year} Q{(day.month - 1) // 3 + 1}"


def _points(values: Floats, ends: Sequence[date]) -> tuple[QuantilePoint, ...]:
    low, middle, high = np.nanquantile(values, (0.1, 0.5, 0.9), axis=0)
    return tuple(
        QuantilePoint(
            period_end=day,
            fiscal_label=_label(day),
            p10=money(float(low[index])),
            p50=money(float(middle[index])),
            p90=money(float(high[index])),
        )
        for index, day in enumerate(ends)
    )


def _observed(case: SimulationCase, name: str) -> tuple[ObservedPoint, ...]:
    field = {"revenue": "revenue", "ebitda": "ebitda", "fcff": "fcf", "net_debt": "net_debt"}[name]
    points: list[ObservedPoint] = []
    for point in case.history:
        value = _value(point, field)
        if value is not None:
            points.append(
                ObservedPoint(
                    period_end=point.period_end,
                    fiscal_label=point.fiscal_label,
                    value=value,
                    filed_at=point.filed_at,
                    source_id=point.source_id,
                )
            )
    return tuple(points)


def _value(point: CaseHistoryPoint, field: str) -> str | None:
    return {
        "revenue": point.revenue,
        "ebitda": point.ebitda,
        "fcf": point.fcf,
        "net_debt": point.net_debt,
    }[field]


def _metrics(
    case: SimulationCase, frame: Frame, ends: Sequence[date], paired: bool
) -> tuple[MetricResult, ...]:
    results = []
    for index, name in enumerate(METRICS):
        metric, label, definition = RESULT_METRICS[name]
        base = frame.metrics[BASELINE, :, :, index]
        alternate = frame.metrics[ALTERNATE, :, :, index]
        forecasts = [ScenarioSeries(scenario="baseline", points=_points(base, ends))]
        changes: tuple[PairedChange, ...] = ()
        if paired:
            forecasts.append(ScenarioSeries(scenario="alt_a", points=_points(alternate, ends)))
            changes = (
                PairedChange(
                    scenario="alt_a",
                    unit=ChangeUnit.CURRENCY,
                    points=_points(alternate - base, ends),
                ),
            )
        results.append(
            MetricResult(
                metric=metric,
                label=label,
                definition=definition,
                observed=_observed(case, name),
                forecasts=tuple(forecasts),
                changes=changes,
            )
        )
    return tuple(results)


def _bins(values: Floats) -> tuple[HistogramBin, ...]:
    low, high = float(values.min()), float(values.max())
    if high - low < 0.01:
        return (HistogramBin(low=money(low - 1), high=money(high + 1), count=int(values.size)),)
    inner_low, inner_high = np.quantile(values, (0.005, 0.995))
    if inner_high - inner_low < 0.01 * BINS:
        inner_low, inner_high = low, high
    edges = np.unique(np.round(np.linspace(inner_low, inner_high, BINS + 1), 2))
    edges[0], edges[-1] = math.floor(low * 100) / 100, math.ceil(high * 100) / 100
    counts, _ = np.histogram(values, bins=edges)
    return tuple(
        HistogramBin(low=money(float(left)), high=money(float(right)), count=int(count))
        for left, right, count in zip(edges[:-1], edges[1:], counts, strict=True)
    )


def _distribution(metric: ResultMetric, change: Floats, day: date) -> ChangeDistribution:
    values = change[np.isfinite(change)]
    return ChangeDistribution(
        metric=metric,
        scenario="alt_a",
        period_end=day,
        bins=_bins(values),
        probability_above_zero=f"{float((values > 0).mean()):.4f}",
        mean=money(float(values.mean())),
    )


def _distributions(frame: Frame, ends: Sequence[date]) -> tuple[ChangeDistribution, ...]:
    found = [_distribution(ResultMetric.EV, ev_change(frame), ends[-1])]
    for index, name in enumerate(METRICS):
        change = frame.metrics[ALTERNATE, :, -1, index] - frame.metrics[BASELINE, :, -1, index]
        found.append(_distribution(RESULT_METRICS[name][0], change, ends[-1]))
    return tuple(found)


def ev_change(frame: Frame) -> Floats:
    """Paired, so only where both scenarios have a value."""
    change: Floats = frame.enterprise[ALTERNATE] - frame.enterprise[BASELINE]
    return change


def _wilson_upper(probability: float, paths: int) -> float:
    """Upper end of a 95% Wilson interval: above zero even when no path had the event."""
    z = 1.96
    centre = probability + z * z / (2 * paths)
    half = z * math.sqrt(probability * (1 - probability) / paths + z * z / (4 * paths * paths))
    return min((centre + half) / (1 + z * z / paths), 1.0)


def _risks(frame: Frame, scenarios: tuple[int, ...]) -> tuple[RiskRow, ...]:
    paths = frame.risks.shape[1]
    rows = []
    for scenario in scenarios:
        for index, risk in enumerate(RISKS):
            probability = float(frame.risks[scenario, :, index].mean())
            rows.append(
                RiskRow(
                    risk=risk,  # type: ignore[arg-type]
                    label=RISK_LABELS[risk],
                    scenario=SCENARIOS[scenario],  # type: ignore[arg-type]
                    probability=round(probability, 5),
                    standard_error=round(math.sqrt(probability * (1 - probability) / paths), 5),
                    upper_95=round(_wilson_upper(probability, paths), 5),
                )
            )
    return tuple(rows)


def _value_row(metric: str, scenario: int, values: Floats) -> ValueRow:
    defined = values[np.isfinite(values)]
    undefined = 1 - defined.size / values.size
    if defined.size == 0:
        return ValueRow(
            metric=metric,  # type: ignore[arg-type]
            scenario=SCENARIOS[scenario],  # type: ignore[arg-type]
            undefined_share=1.0,
        )
    p1, p10, p50, p90, p99 = np.quantile(defined, (0.01, 0.1, 0.5, 0.9, 0.99))
    return ValueRow(
        metric=metric,  # type: ignore[arg-type]
        scenario=SCENARIOS[scenario],  # type: ignore[arg-type]
        p1=money(float(p1)),
        p10=money(float(p10)),
        p50=money(float(p50)),
        p90=money(float(p90)),
        p99=money(float(p99)),
        mean=money(float(defined.mean())),
        undefined_share=round(undefined, 5),
    )


def _values(frame: Frame, scenarios: tuple[int, ...]) -> tuple[ValueRow, ...]:
    rows = []
    for scenario in scenarios:
        rows.append(_value_row("enterprise_value", scenario, frame.enterprise[scenario]))
        rows.append(_value_row("equity_value", scenario, frame.equity[scenario]))
    if ALTERNATE in scenarios:
        rows.append(_value_row("ev_change", ALTERNATE, ev_change(frame)))
    return tuple(rows)


def _quantile_statistic(values: Floats, level: float, count: int) -> tuple[float, float]:
    """A quantile and its error, from the spread of the quantile over sections of the paths."""
    head = values[:count]
    head = head[np.isfinite(head)]
    if head.size < SECTIONS:
        return float("nan"), 0.0
    sections = [float(np.quantile(part, level)) for part in np.array_split(head, SECTIONS)]
    return float(np.quantile(head, level)), float(np.std(sections, ddof=1) / math.sqrt(SECTIONS))


def _share_statistic(values: Floats, count: int) -> tuple[float, float]:
    head = values[:count]
    value = float(head.mean())
    return value, math.sqrt(value * (1 - value) / count)


def _statistics(frame: Frame, count: int, paired: bool) -> dict[str, tuple[str, float, float]]:
    scenario = ALTERNATE if paired else BASELINE
    ebitda = frame.metrics[scenario, :, -1, METRICS.index("ebitda")]
    found: dict[str, tuple[str, float, float]] = {}
    for level, name in ((0.1, "p10"), (0.5, "p50"), (0.9, "p90")):
        found[f"ebitda_{name}"] = (
            f"EBITDA of the last quarter, {name}",
            *_quantile_statistic(ebitda, level, count),
        )
        if paired:
            found[f"ev_change_{name}"] = (
                f"Paired change of EV, {name}",
                *_quantile_statistic(ev_change(frame), level, count),
            )
    for risk in ("funding_shortfall", "covenant_breach", "negative_fcff_year"):
        values = frame.risks[scenario, :, RISKS.index(risk)].astype(np.float64)
        found[f"{risk}_probability"] = (RISK_LABELS[risk], *_share_statistic(values, count))
    return found


def _convergence(frame: Frame, paired: bool) -> tuple[ConvergenceRow, ...]:
    paths = frame.risks.shape[1]
    sizes = sorted({size for size in CONVERGENCE_SIZES if size <= paths} | {paths})
    final = _statistics(frame, paths, paired)
    rows = []
    for size in sizes:
        for name, (label, value, error) in _statistics(frame, size, paired).items():
            if not math.isfinite(value):
                continue
            gap = abs(value - final[name][1])
            rows.append(
                ConvergenceRow(
                    paths=size,
                    statistic=name,
                    label=label,
                    value=round(value, 5),
                    standard_error=round(error, 5),
                    gap_to_final=round(gap, 5),
                    within_two_errors=gap <= 2 * error + 1e-9,
                )
            )
    return tuple(rows)


def _tails(frame: Frame) -> tuple[TailRow, ...]:
    change = ev_change(frame)
    defined = np.flatnonzero(np.isfinite(change))
    worst = defined[np.argsort(change[defined], kind="stable")][:TAIL_ROWS]
    rows = []
    for rank, path in enumerate(worst, start=1):
        growth, margin, rate, closed = frame.tail[path]
        rows.append(
            TailRow(
                rank=rank,
                path=int(path),
                ev_change=money(float(change[path])),
                drivers=(
                    TailDriver(
                        name="growth_shock",
                        label="Average growth shock",
                        value=round(float(growth) * 100, 2),
                        unit="points_of_growth",
                    ),
                    TailDriver(
                        name="margin_shock",
                        label="Average margin shock",
                        value=round(float(margin) * 100, 2),
                        unit="points_of_margin",
                    ),
                    TailDriver(
                        name="rate_shift",
                        label="Short rates at the end",
                        value=round(float(rate) * 100, 2),
                        unit="points_of_rate",
                    ),
                    TailDriver(
                        name="deal_closed",
                        label="The decision went through",
                        value=float(closed),
                        unit="yes_no",
                    ),
                ),
            )
        )
    return tuple(rows)


def drawn_correlation(case: SimulationCase, settings: SimulationSettings) -> tuple[float, float]:
    """Sector growth against sector margin, in the history and in rows actually drawn."""
    model = ShockModel.of(case.shocks, settings)
    growth, margin = model.column(SECTOR_GROWTH), model.column(SECTOR_MARGIN)
    rng = generator(settings.seed, 0, 2, 0)
    rows = np.concatenate(
        [
            model.table[block_indices(rng, len(model.table), case.horizon, model.mean_block)]
            for _ in range(CORRELATION_DRAWS)
        ]
    )
    history = float(np.corrcoef(model.table[:, growth], model.table[:, margin])[0, 1])
    return history, float(np.corrcoef(rows[:, growth], rows[:, margin])[0, 1])


def _planning_flags(decision: DecisionModel) -> list[str]:
    """A setting outside the planning range is allowed, and is named."""
    spec = CATALOG.spec(decision.type)
    flags = []
    for parameter in spec.parameters:
        if parameter.planning is None:
            continue
        value = getattr(decision, parameter.key)
        points = [value] if isinstance(value, str | int) else distribution_points(value)
        if any(not parameter.planning.contains(Decimal(str(point))) for point in points):
            flags.append(f"Out of distribution: {parameter.label} is outside the planning range.")
    return flags


def _flags(
    frame: Frame,
    decision: DecisionModel | None,
    convergence: Sequence[ConvergenceRow],
    clipped: float,
    undefined: float,
) -> tuple[str, ...]:
    paths = frame.risks.shape[1]
    flags = []
    if paths < TAIL_PATHS:
        flags.append(f"Fewer than {TAIL_PATHS} paths: tail probabilities near 1% are not resolved.")
    sizes = sorted({row.paths for row in convergence})
    if len(sizes) > 1:
        size = sizes[-2]
        unsettled = sorted(
            {
                row.statistic
                for row in convergence
                if row.paths == size and not row.within_two_errors
            }
        )
        if unsettled:
            flags.append(f"Not settled at {size} paths: {', '.join(unsettled)}.")
    if int(np.isnan(frame.metrics[BASELINE, :, 0, 0]).sum()):
        flags.append("Some paths were abandoned after their redraws.")
    if clipped > 0.01:
        flags.append(f"Hard bounds were met in {clipped:.1%} of quarters: the shocks are large.")
    if undefined > 0.05:
        flags.append(f"Value is undefined on {undefined:.1%} of paths.")
    revenue = frame.metrics[BASELINE, :, -1, METRICS.index("revenue")]
    low, high = np.nanquantile(revenue, (0.01, 0.99))
    if low > 0 and high / low > 20:
        flags.append("Revenue at the horizon spreads over 20 times: the long end is unstable.")
    if decision is not None:
        flags.extend(_planning_flags(decision))
    return tuple(flags)


def _events(case: SimulationCase, decision: DecisionModel | None) -> tuple[TimelineEvent, ...]:
    events = [TimelineEvent(on=case.as_of, label="Knowledge cutoff", kind="cutoff")]
    if decision is None:
        return tuple(events)
    timing = decision.timing
    start = add_quarters(timing.effective_date, timing.lag_quarters)
    full = add_quarters(start, timing.ramp_quarters)
    return (
        *events,
        TimelineEvent(
            on=timing.announcement_date,
            label="Announced",
            kind="announcement",
            scenario="alt_a",
        ),
        TimelineEvent(
            on=timing.effective_date, label="Takes effect", kind="effective", scenario="alt_a"
        ),
        TimelineEvent(on=start, label="First effect", kind="effect_start", scenario="alt_a"),
        TimelineEvent(on=full, label="Full effect", kind="full_effect", scenario="alt_a"),
    )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def report_identity(
    case: SimulationCase, decision: DecisionModel | None, settings: SimulationSettings
) -> tuple[str, str, str]:
    """The report id, and the hashes of the case and the decision."""
    case_sha = _sha(case.model_dump_json())
    decision_sha = _sha(decision.model_dump_json() if decision is not None else "baseline")
    parts = (
        case_sha,
        decision_sha,
        settings.model_dump_json(),
        finance_version,
        simulation_version,
        CONTRACTS_VERSION,
    )
    digest = _sha("|".join(parts))[:12]
    return f"sim-{case.as_of:%Y%m%d}-{digest}", case_sha, decision_sha


def build_report(
    case: SimulationCase,
    decision: DecisionModel,
    settings: SimulationSettings,
    frame: Frame,
    *,
    code_version: str,
    created_at: datetime,
    seconds: float,
    sensitivity: tuple[SensitivityRow, ...] = (),
) -> SimulationReport:
    ends = quarter_ends(case.balance_date, case.horizon)
    report_id, case_sha, decision_sha = report_identity(case, decision, settings)
    result_id = str(uuid.uuid5(uuid.NAMESPACE_URL, report_id))
    synthetic = case.data_origin is DataOrigin.SYNTHETIC
    mode = ResultMode.DEMO if synthetic else ResultMode.EMPIRICAL_FORECAST
    scenarios = (BASELINE, ALTERNATE)
    convergence = _convergence(frame, True)
    clipped = float(frame.clipped.sum()) / (settings.paths * case.horizon * 2)
    undefined = float(np.isnan(frame.enterprise).mean())
    historical, simulated = drawn_correlation(case, settings)
    model_text = (
        f"stationary block bootstrap of {len(case.shocks.rows)} calendar quarters, mean block "
        f"{settings.mean_block_quarters or case.shocks.mean_block_quarters:g}, scale "
        f"{settings.shock_scale:g}, macro {'locked' if settings.lock_macro else 'free'}"
    )
    stamp = datetime.combine(case.as_of, time(23, 59, 59), tzinfo=UTC)
    result = ScenarioResult(
        result_id=result_id,
        title=f"{case.company_name}: {CATALOG.spec(decision.type).label}",
        status=ResultStatus.COMPLETED,
        mode=mode,
        data_origin=case.data_origin,
        mock=False,
        company_id=case.company_id,
        company_name=case.company_name,
        as_of=case.as_of,
        currency=case.currency,
        horizon_quarters=case.horizon,
        paths=settings.paths,
        seed=settings.seed,
        model=case.model_id or "transparent central path",
        uncertainty_type=UncertaintyType.CONDITIONAL_MODEL_QUANTILES,
        calibrated=False,
        scenarios=(
            ScenarioRun(key="baseline", label="Baseline"),
            ScenarioRun(key="alt_a", label=CATALOG.spec(decision.type).label, decision=decision),
        ),
        metrics=_metrics(case, frame, ends, True),
        distributions=_distributions(frame, ends),
        events=_events(case, decision),
        manifest=ReproducibilityManifest(
            contracts_version=CONTRACTS_VERSION,
            scenario_id=result_id,
            revision=1,
            mode=mode,
            data_origin=case.data_origin,
            causal_status=CausalStatus.ASSUMPTION_BASED,
            as_of=stamp,
            seed=settings.seed,
            code_version=code_version,
            dataset_snapshot_id=case.dataset_id,
            model_id=case.model_id,
            generated_at=created_at,
        ),
        created_at=created_at,
    )
    return SimulationReport(
        manifest=SimulationManifest(
            report_id=report_id,
            contracts_version=CONTRACTS_VERSION,
            finance_version=finance_version,
            simulation_version=simulation_version,
            code_version=code_version,
            case_id=case.case_id,
            case_sha256=case_sha,
            decision_sha256=decision_sha,
            dataset_id=case.dataset_id,
            dataset_sha256=case.dataset_sha256,
            model_id=case.model_id,
            settings=settings,
            shock_model=model_text,
            created_at=created_at,
        ),
        validation="conditional_non_validated",
        probability_label=CONDITIONAL_LABEL,  # type: ignore[arg-type]
        result=result,
        risks=_risks(frame, scenarios),
        values=_values(frame, scenarios),
        convergence=convergence,
        tails=_tails(frame),
        sensitivity=sensitivity,
        inputs=case.inputs,
        diagnostics=SimulationDiagnostics(
            paths=settings.paths,
            redraws=int(frame.redraws.sum()),
            invalid_by_code=tuple(sorted(frame.invalid.items())),
            clipped_share=round(clipped, 6),
            ev_undefined_share=round(undefined, 6),
            path_identities_checked=max(int(np.isfinite(frame.metrics[:, :, 0, 0]).sum()), 1),
            history_quarters=len(case.shocks.rows),
            simulated_correlation=round(simulated, 4),
            historical_correlation=round(historical, 4),
            effective_sample_size=float(settings.paths),
            seconds=round(seconds, 2),
            flags=_flags(frame, decision, convergence, clipped, undefined),
        ),
    )
