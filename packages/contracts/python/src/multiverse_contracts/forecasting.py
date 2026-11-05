"""Forecasting baselines: the point-in-time dataset, the locked protocol and the benchmark.

Stage 15 compares simple models before any neural network (docs/06). Every model sees the
same rows: features as known at the forecast origin (vintage view), targets as first
released, each with the moment it was released. The protocol is written before the test
period is scored and named by its SHA-256; the benchmark names the dataset and protocol
it used, so a number can always be traced to its inputs.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

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


class SequenceManifest(ContractModel):
    """Quarterly histories aligned with the rows of a forecasting dataset (Stage 16)."""

    sequences_id: Annotated[str, StringConstraints(pattern=r"^fsq-[0-9]{8}-[0-9a-f]{12}$")]
    sha256: Sha256
    dataset_id: str
    dataset_sha256: Sha256
    lags: int = Field(ge=1, le=40, description="Lags 1 to this one; lag 0 is never public.")
    channels: tuple[Name, ...] = Field(min_length=1)
    rows: int = Field(ge=0, description="Company origins, each with every lag.")
    contracts_version: str
    created_at: AwareDatetime = Field(description="Not part of the hash.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.sequences_id.rsplit("-", 1)[1] != self.sha256[:12]:
            raise ValueError("the sequences are named by their SHA-256")
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
    repeats: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Trainings per test fold, with seeds seed, seed + 1, ...: each is scored, "
        "and so is the mean of their forecasts.",
    )
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


class EpochLog(ContractModel):
    epoch: int = Field(ge=1)
    train_loss: Score
    validation_loss: Score
    learning_rate: Score
    seconds: Score


class TrainingRun(ContractModel):
    """One training of a temporal model: what it saw, how it went, where it is stored."""

    run_id: Annotated[str, StringConstraints(pattern=r"^run-[0-9]{8}-[0-9a-f]{12}$")]
    model: Name
    purpose: Literal["smoke", "benchmark", "job"]
    dataset_id: str
    sequences_id: str
    fold_year: int
    seed: int
    device: str
    torch_version: str
    params: tuple[Param, ...]
    train_rows: int = Field(ge=1)
    validation_rows: int = Field(ge=1)
    evaluated_rows: int = Field(ge=0)
    epochs: tuple[EpochLog, ...] = Field(min_length=1)
    best_epoch: int = Field(ge=1)
    checkpoint_sha256: Sha256
    created_at: AwareDatetime = Field(description="Not part of the id.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.best_epoch > len(self.epochs):
            raise ValueError("the best epoch is one of the epochs run")
        return self


class ApprovalRule(ContractModel):
    """Which forecasts may leave Stage 17: written down before anything is scored."""

    horizons: tuple[int, ...] = Field(min_length=1)
    min_examples: int = Field(ge=1, description="Rows of the final years, per target and horizon.")
    coverage_tolerance: Score = Field(description="Allowed gap to each nominal coverage.")
    cold_start_tolerance: Score = Field(description="The same gap for firms never trained on.")


class EvaluationProtocol(ContractModel):
    """Written before Stage 17 scored anything; its SHA-256 goes into the package."""

    protocol_id: Name
    base_protocol_id: Name
    base_protocol_sha256: Sha256
    benchmark_id: str = Field(description="The Stage 16 benchmark whose chosen settings it uses.")
    seed: int
    levels: tuple[float, ...] = Field(min_length=3)
    nominal: tuple[float, ...] = Field(min_length=1)
    development_years: tuple[int, ...] = Field(
        min_length=1, description="Choose the architecture and whether to calibrate."
    )
    final_years: tuple[int, ...] = Field(min_length=1, description="Scored last, for the verdict.")
    repeats: int = Field(ge=1, le=10)
    ablation_repeats: int = Field(ge=1, le=10)
    ablations: tuple[Name, ...] = ()
    ood_z: Score = Field(description="A row is out of distribution beyond this many deviations.")
    sparse_quarters: int = Field(ge=1, description="Below this many observed quarters: sparse.")
    dense_quarters: int = Field(ge=1, description="At this many observed quarters: dense.")
    approval: ApprovalRule

    @model_validator(mode="after")
    def _check(self) -> Self:
        if max(self.development_years) >= min(self.final_years):
            raise ValueError("development years come before the final years")
        if self.ablation_repeats > self.repeats:
            raise ValueError("an ablation repeats no more than the full model")
        if sorted(self.levels) != list(self.levels) or 0.5 not in self.levels:
            raise ValueError("levels are in order and include the median")
        return self


class BandScore(ContractModel):
    """The quantile forecasts of one model on one set of rows, in the target's training space."""

    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    split: SplitName
    population: Population = Population.ALL
    period: Name
    model: Name
    calibrated: bool
    examples: int = Field(ge=0)
    companies: int = Field(ge=0)
    pinball: Score
    pinball_low: Score = Field(description="95% interval, bootstrap over companies.")
    pinball_high: Score
    wis: Score = Field(description="Weighted interval score, a finite approximation of CRPS.")
    median_ae: Score = Field(description="Of the median forecast, in the target's own units.")
    coverage: tuple[Score, ...] = Field(description="Per nominal coverage of the protocol.")
    coverage_low: tuple[Score, ...]
    coverage_high: tuple[Score, ...]
    width: tuple[Score, ...] = Field(description="Mean width per nominal coverage.")
    median_width: tuple[Score, ...]
    reliability: tuple[Score, ...] = Field(description="Share of actuals below each level.")
    vs_persistence: Score | None = Field(
        default=None, description="Pinball over that of the persistence band, minus one."
    )
    vs_persistence_low: Score | None = None
    vs_persistence_high: Score | None = None
    vs_best: Score | None = Field(
        default=None, description="Pinball over that of the best baseline band, minus one."
    )
    vs_best_low: Score | None = None
    vs_best_high: Score | None = None
    best_baseline: Name | None = None


class SliceScore(ContractModel):
    """One model on one slice of the rows: a year, a sector, a history length, a condition."""

    kind: Literal["year", "division", "history", "distribution"]
    value: str = Field(min_length=1, max_length=40)
    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    model: Name
    examples: int = Field(ge=0)
    companies: int = Field(ge=0)
    pinball: Score
    vs_persistence: Score
    coverage: tuple[Score, ...]


class CompanyErrors(ContractModel):
    """How errors spread over firms: a mean over rows hides the firm it fails."""

    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    model: Name
    companies: int = Field(ge=0)
    examples: int = Field(ge=0)
    examples_per_firm_median: Score
    pinball_p10: Score
    pinball_p50: Score
    pinball_p90: Score
    better_than_persistence: Score = Field(description="Share of firms with a lower pinball.")


class AblationScore(ContractModel):
    name: Name
    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    examples: int = Field(ge=0)
    pinball: Score
    change: Score = Field(description="Pinball over that of the full model, minus one.")
    change_low: Score
    change_high: Score


class MemorizationScore(ContractModel):
    """Pinball where the model could remember a firm, and where it could not."""

    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    trained: Score = Field(description="Rows it was fitted on.")
    watched: Score = Field(description="Same period, firms that only stopped the training.")
    test_seen: Score = Field(description="Test rows of firms it was fitted on.")
    test_cold: Score = Field(description="Test rows of firms it never saw.")
    cold_change: Score = Field(description="Cold over seen, each set against persistence.")
    cold_change_low: Score
    cold_change_high: Score


class StabilityScore(ContractModel):
    """Forecasts of one quarter from two origins, and the disagreement between seeds."""

    target: ForecastTarget
    long_horizon: int = Field(ge=1, le=40)
    short_horizon: int = Field(ge=1, le=40)
    pairs: int = Field(ge=0)
    median_revision: Score
    median_error: Score = Field(description="Of the later forecast.")
    median_seed_spread: Score = Field(description="Between the seeds, at the long horizon.")


class ApprovalRow(ContractModel):
    target: ForecastTarget
    horizon: int = Field(ge=1, le=40)
    examples: int = Field(ge=0)
    enough_examples: bool
    coverage_seen: bool
    coverage_cold: bool
    beats_persistence: bool
    not_worse_than_best: bool
    typical_firm: bool
    approved: bool


class EvaluationPackage(ContractModel):
    """Stage 17: what the quantile forecasts are worth, measured, with every failure kept."""

    evaluation_id: Annotated[str, StringConstraints(pattern=r"^eval-[0-9]{8}-[0-9a-f]{12}$")]
    sha256: Sha256 = Field(description="Of the scores, the stored forecasts and the inputs.")
    dataset_id: str
    dataset_sha256: Sha256
    sequences_id: str
    protocol_id: Name
    protocol_sha256: Sha256
    benchmark_id: str
    bands_sha256: Sha256
    model_id: Annotated[str, StringConstraints(pattern=r"^model-[0-9]{8}-[0-9a-f]{12}$")]
    primary_model: Name
    calibrated: bool
    scores: tuple[BandScore, ...] = Field(min_length=1)
    slices: tuple[SliceScore, ...] = ()
    companies: tuple[CompanyErrors, ...] = ()
    ablations: tuple[AblationScore, ...] = ()
    memorization: tuple[MemorizationScore, ...] = ()
    stability: tuple[StabilityScore, ...] = ()
    approvals: tuple[ApprovalRow, ...] = ()
    findings: tuple[Text, ...] = Field(min_length=1)
    failures: tuple[Text, ...] = ()
    contracts_version: str
    created_at: AwareDatetime = Field(description="Not part of the hash.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.evaluation_id.rsplit("-", 1)[1] != self.sha256[:12]:
            raise ValueError("the evaluation is named by its SHA-256")
        return self
