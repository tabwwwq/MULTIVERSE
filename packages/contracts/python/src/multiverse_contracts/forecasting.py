"""Forecasting baselines: the point-in-time dataset, the locked protocol and the benchmark.

Stage 15 compares simple models before any neural network (docs/06). Every model sees the
same rows: features as known at the forecast origin (vintage view), targets as first
released, each with the moment it was released. The protocol is written before the test
period is scored and named by its SHA-256; the benchmark names the dataset and protocol
it used, so a number can always be traced to its inputs.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.normalized import Text
from multiverse_contracts.pit import KnowledgeView, Sha256
from multiverse_contracts.primitives import ContractModel

Name = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
Score = Annotated[float, Field(allow_inf_nan=False)]


class ForecastTarget(StrEnum):
    REVENUE_GROWTH = "revenue_growth"
    """Symmetric growth of the target quarter over the same quarter a year earlier:
    (a - b) / ((a + b) / 2), between -2 and 2."""
    OPERATING_MARGIN = "operating_margin"
    EBITDA_MARGIN = "ebitda_margin"
    FCF_MARGIN = "fcf_margin"
    DEBT_TO_EBITDA = "debt_to_ebitda"
    """Debt at the quarter end over EBITDA of the four quarters to it; undefined when not
    positive."""


class SplitName(StrEnum):
    VALIDATION = "validation"
    """Earlier origins of the training firms: chooses hyperparameters, nothing else."""
    TEST = "test"
    """Later origins of the training firms: scored once, with the chosen settings."""
    COLD_START = "cold_start"
    """The same later origins of firms never seen in training."""


class Population(StrEnum):
    ALL = "all"
    """Every scoreable row."""
    MATERIAL = "revenue_10m"
    """Firms with at least $10 million of revenue in the four quarters before the origin,
    as known at the origin: margins of near-zero revenues swamp every error measure."""


class TargetCount(ContractModel):
    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    defined: int = Field(ge=0)
    undefined: int = Field(ge=0, description="Released, but the ratio has no meaning.")


class ForecastDatasetManifest(ContractModel):
    dataset_id: Annotated[str, StringConstraints(pattern=r"^fds-[0-9]{8}-[0-9a-f]{12}$")]
    sha256: Sha256
    universe_id: Text
    pit_built_at: AwareDatetime
    data_cutoff: AwareDatetime
    view: KnowledgeView
    first_origin: date
    last_origin: date
    horizons: tuple[int, ...] = Field(min_length=1)
    targets: tuple[ForecastTarget, ...] = Field(min_length=1)
    features: tuple[Name, ...] = Field(min_length=1)
    macro_series: tuple[Text, ...] = ()
    rows: int = Field(ge=0)
    companies: int = Field(ge=0)
    target_counts: tuple[TargetCount, ...] = ()
    contracts_version: str
    created_at: AwareDatetime = Field(description="Not part of the hash.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.view is not KnowledgeView.VINTAGE:
            raise ValueError("features are what was known at each origin: the vintage view")
        if self.dataset_id.rsplit("-", 1)[1] != self.sha256[:12]:
            raise ValueError("the dataset is named by its SHA-256")
        if self.first_origin > self.last_origin:
            raise ValueError("origins run forward")
        return self


class Param(ContractModel):
    name: Name
    value: str = Field(min_length=1, max_length=80)


class ForecastProtocol(ContractModel):
    """Written before the test period is scored; its SHA-256 goes into every report."""

    protocol_id: Name
    seed: int
    targets: tuple[ForecastTarget, ...] = Field(min_length=1)
    horizons: tuple[int, ...] = Field(min_length=1)
    validation_years: tuple[int, ...] = Field(min_length=1)
    test_years: tuple[int, ...] = Field(min_length=1)
    cold_start_share: float = Field(gt=0, lt=1)
    material_revenue: float = Field(gt=0, description="Revenue floor of the material population.")
    winsor_quantile: float = Field(ge=0, lt=0.5)
    bootstrap_resamples: int = Field(ge=100)
    grids: dict[Name, tuple[tuple[Param, ...], ...]]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if max(self.validation_years) >= min(self.test_years):
            raise ValueError("validation years come before the test years")
        if sorted(set(self.horizons)) != list(self.horizons):
            raise ValueError("horizons are listed once each, in order")
        return self


class ModelConfig(ContractModel):
    target: ForecastTarget
    model: Name
    params: tuple[Param, ...] = ()
    validation_mae: Score | None = Field(default=None, description="Of the chosen setting.")


class ScoreRow(ContractModel):
    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    split: SplitName
    population: Population = Population.ALL
    model: Name
    examples: int = Field(ge=0)
    companies: int = Field(ge=0)
    mae: Score
    rmse: Score
    median_ae: Score
    wape: Score | None = Field(default=None, description="None when actuals sum to zero.")
    firm_weighted_mae: Score
    revenue_weighted_mae: Score
    mae_low: Score = Field(description="95% interval, bootstrap over companies.")
    mae_high: Score
    vs_naive: Score | None = Field(
        default=None, description="MAE over the persistence MAE on the same rows, minus one."
    )
    vs_naive_low: Score | None = None
    vs_naive_high: Score | None = None


class SectorScore(ContractModel):
    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    split: SplitName
    model: Name
    division: Annotated[str, StringConstraints(pattern=r"^[A-K]$")]
    examples: int = Field(ge=0)
    mae: Score


class BenchmarkReport(ContractModel):
    benchmark_id: Annotated[str, StringConstraints(pattern=r"^bench-[0-9]{8}-[0-9a-f]{12}$")]
    sha256: Sha256 = Field(description="Of the scores, configurations and inputs.")
    dataset_id: str
    dataset_sha256: Sha256
    protocol_id: Name
    protocol_sha256: Sha256
    seed: int
    configs: tuple[ModelConfig, ...] = Field(min_length=1)
    scores: tuple[ScoreRow, ...] = Field(min_length=1)
    sectors: tuple[SectorScore, ...] = ()
    findings: tuple[Text, ...] = Field(min_length=1)
    failures: tuple[Text, ...] = ()
    contracts_version: str
    created_at: AwareDatetime = Field(description="Not part of the hash.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.benchmark_id.rsplit("-", 1)[1] != self.sha256[:12]:
            raise ValueError("the benchmark is named by its SHA-256")
        return self
