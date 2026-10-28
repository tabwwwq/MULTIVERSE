"""Result of a scenario run: history, quantile paths, paired differences (docs/08, docs/09).

A result compares a baseline with up to two alternates for one company at one knowledge
cutoff. Alternates share the baseline's random shocks path by path (paired paths, PRD
FR-SI-07), so differences are computed per path and stored on their own: the quantile
of a difference is not the difference of quantiles.

Stage 06 fills this contract with mock results only (``mock = True``); the Monte Carlo
engine of Stage 22 produces the real ones.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from multiverse_contracts.decisions import Decision
from multiverse_contracts.manifest import ReproducibilityManifest
from multiverse_contracts.primitives import (
    ContractModel,
    CurrencyCode,
    DataOrigin,
    DecimalString,
    ResultMode,
    UncertaintyType,
)

_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

ScenarioKey = Literal["baseline", "alt_a", "alt_b"]


class ResultMetric(StrEnum):
    REVENUE = "revenue"
    EBITDA = "ebitda"
    FCF = "fcf"
    NET_DEBT = "net_debt"
    EV = "ev"


class ResultStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ChangeUnit(StrEnum):
    """Unit of a paired difference: dollars, or a fraction of the baseline value."""

    CURRENCY = "currency"
    FRACTION_OF_BASELINE = "fraction_of_baseline"


class ObservedPoint(ContractModel):
    """A reported quarter, public by the cutoff."""

    period_end: date
    fiscal_label: str = Field(min_length=1, description="For example 'FY2022 Q3'.")
    value: DecimalString
    filed_at: date
    source_id: str = Field(min_length=1)


class QuantilePoint(ContractModel):
    """Quantiles across paths for one quarter. p10 <= p50 <= p90."""

    period_end: date
    fiscal_label: str = Field(min_length=1)
    p10: DecimalString
    p50: DecimalString
    p90: DecimalString

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not Decimal(self.p10) <= Decimal(self.p50) <= Decimal(self.p90):
            raise ValueError(f"{self.fiscal_label}: quantiles must satisfy p10 <= p50 <= p90")
        return self


class ScenarioSeries(ContractModel):
    scenario: ScenarioKey
    points: tuple[QuantilePoint, ...] = Field(min_length=1)


class PairedChange(ContractModel):
    """Alternate minus baseline, computed path by path, as quantiles."""

    scenario: Literal["alt_a", "alt_b"]
    unit: ChangeUnit
    points: tuple[QuantilePoint, ...] = Field(min_length=1)


class MetricResult(ContractModel):
    metric: ResultMetric
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    observed: tuple[ObservedPoint, ...]
    forecasts: tuple[ScenarioSeries, ...] = Field(min_length=1)
    changes: tuple[PairedChange, ...] = ()


class HistogramBin(ContractModel):
    low: DecimalString
    high: DecimalString
    count: int = Field(ge=0)


class ChangeDistribution(ContractModel):
    """Distribution of one paired difference at the horizon (docs/08 delta distributions)."""

    metric: ResultMetric
    scenario: Literal["alt_a", "alt_b"]
    period_end: date
    bins: tuple[HistogramBin, ...] = Field(min_length=1)
    probability_above_zero: DecimalString = Field(
        description="Share of paths where the alternate beats the baseline, under the model."
    )
    mean: DecimalString

    @model_validator(mode="after")
    def _bins_tile(self) -> Self:
        for previous, current in pairwise(self.bins):
            if Decimal(previous.high) != Decimal(current.low):
                raise ValueError("histogram bins must be contiguous")
        if any(Decimal(b.low) >= Decimal(b.high) for b in self.bins):
            raise ValueError("each bin needs low < high")
        if not 0 <= Decimal(self.probability_above_zero) <= 1:
            raise ValueError("probability_above_zero is a fraction")
        return self


class WaterfallStep(ContractModel):
    label: str = Field(min_length=1)
    value: DecimalString
    explanation: str = Field(min_length=1)


class Waterfall(ContractModel):
    """Bridge from the baseline to an alternate. Means are used because means add up."""

    metric: ResultMetric
    scenario: Literal["alt_a", "alt_b"]
    period_end: date
    aggregation: Literal["quarter", "cumulative"] = Field(
        description="The value in the quarter ending period_end, or the sum up to it."
    )
    statistic: Literal["mean"]
    start: DecimalString
    steps: tuple[WaterfallStep, ...] = Field(min_length=1)
    end: DecimalString

    @model_validator(mode="after")
    def _adds_up(self) -> Self:
        total = Decimal(self.start) + sum(Decimal(step.value) for step in self.steps)
        if total != Decimal(self.end):
            raise ValueError("waterfall steps must add up exactly from start to end")
        return self


class TimelineEvent(ContractModel):
    on: date
    label: str = Field(min_length=1)
    kind: Literal["cutoff", "announcement", "effective", "effect_start", "full_effect"]
    scenario: ScenarioKey | None = None


class ScenarioRun(ContractModel):
    key: ScenarioKey
    label: str = Field(min_length=1)
    decision: Decision | None = None


class ResultFailure(ContractModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    message: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)


class ScenarioResult(ContractModel):
    """One run: a baseline and its alternates for a company at a knowledge cutoff."""

    result_id: str = Field(pattern=_UUID)
    title: str = Field(min_length=1)
    status: ResultStatus
    mode: ResultMode
    data_origin: DataOrigin
    mock: bool = Field(description="Generated without a model, for interface work only.")
    company_id: str = Field(pattern=_UUID)
    company_name: str = Field(min_length=1)
    as_of: date
    currency: CurrencyCode
    horizon_quarters: int = Field(ge=1, le=40)
    paths: int = Field(ge=1)
    seed: int = Field(ge=0)
    model: str = Field(min_length=1)
    uncertainty_type: UncertaintyType
    calibrated: bool
    scenarios: tuple[ScenarioRun, ...] = ()
    metrics: tuple[MetricResult, ...] = ()
    distributions: tuple[ChangeDistribution, ...] = ()
    waterfalls: tuple[Waterfall, ...] = ()
    events: tuple[TimelineEvent, ...] = ()
    failure: ResultFailure | None = None
    manifest: ReproducibilityManifest
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _check_result(self) -> Self:
        if self.mode is ResultMode.DEMO and (
            self.data_origin is not DataOrigin.SYNTHETIC or self.calibrated
        ):
            raise ValueError("a demo result is synthetic and never calibrated (SYN-01, FP-03)")
        if self.mock and self.mode is not ResultMode.DEMO:
            raise ValueError("a mock result can only be shown in demo mode")
        if self.manifest.scenario_id != self.result_id or self.manifest.seed != self.seed:
            raise ValueError("the manifest must describe this result")

        if self.status is ResultStatus.FAILED:
            if self.failure is None or self.metrics or self.distributions or self.waterfalls:
                raise ValueError("a failed result has a failure and no numbers")
            return self
        if self.failure is not None:
            raise ValueError("only a failed result has a failure")
        self._check_scenarios()
        self._check_metrics()
        return self

    def _check_scenarios(self) -> None:
        keys = [run.key for run in self.scenarios]
        if not keys or keys[0] != "baseline" or len(set(keys)) != len(keys):
            raise ValueError("scenarios start with the baseline and are unique")
        for run in self.scenarios:
            if (run.key == "baseline") != (run.decision is None):
                raise ValueError("only alternates carry a decision")
        alternates = set(keys) - {"baseline"}
        if not alternates:
            raise ValueError("a completed result compares at least one alternate")
        used = [d.scenario for d in self.distributions] + [w.scenario for w in self.waterfalls]
        for scenario in used:
            if scenario not in alternates:
                raise ValueError(f"unknown scenario {scenario}")

    def _check_metrics(self) -> None:
        keys = {run.key for run in self.scenarios}
        if not self.metrics:
            raise ValueError("a completed result has metrics")
        for metric in self.metrics:
            if {series.scenario for series in metric.forecasts} != keys:
                raise ValueError(f"{metric.metric}: one forecast per scenario")
            last_observed = max((point.period_end for point in metric.observed), default=None)
            for series in metric.forecasts:
                if len(series.points) != self.horizon_quarters:
                    raise ValueError(f"{metric.metric}: forecasts cover the horizon")
                if last_observed and series.points[0].period_end <= last_observed:
                    raise ValueError(f"{metric.metric}: forecasts start after the history")
            for change in metric.changes:
                if change.scenario not in keys:
                    raise ValueError(f"{metric.metric}: change for an unknown scenario")
                if len(change.points) != self.horizon_quarters:
                    raise ValueError(f"{metric.metric}: changes cover the horizon")
            for point in metric.observed:
                if point.filed_at > self.as_of:
                    raise ValueError(f"{metric.metric}: history includes a value filed after as_of")
