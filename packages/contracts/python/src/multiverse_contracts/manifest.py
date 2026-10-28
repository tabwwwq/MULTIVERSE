"""Reproducibility manifest: everything needed to replay a result exactly.

Sources: docs/03 (Versioning), PRD FR-RP-02, SYN-01, FR-CA-02.
"""

from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from multiverse_contracts.primitives import CausalStatus, ContractModel, DataOrigin, ResultMode

_SEMVER = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"


class ReproducibilityManifest(ContractModel):
    """Identity card of one result. Two results with equal manifests must be identical."""

    contracts_version: str = Field(pattern=_SEMVER)
    scenario_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    mode: ResultMode
    data_origin: DataOrigin
    causal_status: CausalStatus = CausalStatus.NOT_ASSESSED
    as_of: AwareDatetime
    seed: int = Field(ge=0)
    code_version: str = Field(min_length=1, description="Git commit, or 'unversioned'.")
    dataset_snapshot_id: str | None = None
    model_id: str | None = None
    source_ids: tuple[str, ...] = ()
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def _check_mode_rules(self) -> Self:
        is_demo = self.mode is ResultMode.DEMO
        is_synthetic = self.data_origin is DataOrigin.SYNTHETIC
        if is_demo != is_synthetic:
            raise ValueError("demo mode and synthetic data always go together (PRD SYN-01)")
        if self.mode in (ResultMode.EMPIRICAL_FORECAST, ResultMode.CAUSAL_STUDY) and (
            self.dataset_snapshot_id is None or self.model_id is None
        ):
            raise ValueError(f"mode '{self.mode}' requires dataset_snapshot_id and model_id")
        if self.causal_status is CausalStatus.DIAGNOSTICS_PASSED and (
            self.mode is not ResultMode.CAUSAL_STUDY
        ):
            raise ValueError("diagnostics_passed is only possible in a causal study")
        if self.mode is ResultMode.CAUSAL_STUDY and self.causal_status is CausalStatus.NOT_ASSESSED:
            raise ValueError("a causal study must state its causal status")
        return self
