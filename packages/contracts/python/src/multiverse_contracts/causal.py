"""Causal research design and feasibility (Stage 20): what could be claimed, and what not yet.

A study states its graph, estimands and assumptions, and measures whether a method could
identify anything: support, balance, pre-trends, placebo dates, the spread of effects where
there are none. It reads no outcome after a treatment: effects stay unestimated until the
registry audit of Stage 19 opens the gate.
"""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from multiverse_contracts.events import EventType
from multiverse_contracts.forecasting import Name, Score
from multiverse_contracts.normalized import Text
from multiverse_contracts.pit import Sha256
from multiverse_contracts.primitives import ContractModel


class CausalNode(ContractModel):
    node_id: Name
    label: str = Field(min_length=1, max_length=60)
    role: Literal["macro", "state", "unobserved", "action", "mediator", "outcome"]
    observed: bool
    measured_by: Text = Field(description="The data behind it, or why there is none.")


class CausalEdge(ContractModel):
    source: Name
    target: Name
    rationale: Text


class CausalGraph(ContractModel):
    """A hypothesis, never a finding: drawn from reasoning, not discovered from data."""

    nodes: tuple[CausalNode, ...] = Field(min_length=1)
    edges: tuple[CausalEdge, ...] = Field(min_length=1)
    omitted: tuple[Text, ...] = Field(description="What the graph leaves out, said aloud.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        known = {n.node_id for n in self.nodes}
        if any(e.source not in known or e.target not in known for e in self.edges):
            raise ValueError("every edge joins two nodes of the graph")
        return self


class BalanceRow(ContractModel):
    covariate: Name
    before: Score = Field(description="Standardized mean difference against all controls.")
    after: Score = Field(description="Against the matched controls.")


class LeadRow(ContractModel):
    """Treated minus matched control before the event, against the last quarter before it."""

    outcome: Name
    lead: int = Field(le=-2, description="Quarters before the event quarter.")
    mean: Score
    low: Score
    high: Score
    events: int = Field(ge=0)


class PlaceboRow(ContractModel):
    """A false event date inside the pre-period: any effect found here is not one."""

    outcome: Name
    shift: int = Field(ge=1, description="Quarters before the true event.")
    estimate: Score
    low: Score
    high: Score
    events: int = Field(ge=0)


class NullRow(ContractModel):
    """Pseudo-events on firms without the action: what chance alone produces."""

    outcome: Name
    draws: int = Field(ge=1)
    pseudo_events: int = Field(ge=0, description="Per draw, as many as usable treated events.")
    spread: Score = Field(description="Standard deviation of the mean over the draws.")
    false_positive_rate: Score = Field(description="Draws rejected at a nominal 5%.")
    minimum_effect_now: Score = Field(description="Detectable at 80% power with today's events.")
    minimum_effect_pool: Score = Field(description="The same with every candidate of the index.")
    e_value: Score = Field(description="Hidden confounding that could explain that minimum.")


class SyntheticFit(ContractModel):
    """Fit of a synthetic control on the pre-period only."""

    usable: int = Field(ge=0, description="Events with enough quarters and donors.")
    median_donors: Score
    median_holdout_ratio: Score | None = Field(
        default=None, description="Error on held-out pre-quarters over the error of the fit."
    )


class MethodVerdict(ContractModel):
    method: Literal["matched_cohort", "weighted_regression", "did_event_study", "synthetic_control"]
    feasible: bool
    reasons: tuple[Text, ...]


class TreatmentStudy(ContractModel):
    treatment: EventType
    estimand: Text
    assumptions: tuple[Text, ...] = Field(min_length=1)
    untested: tuple[Text, ...] = Field(description="Assumptions no diagnostic here can check.")
    events: int = Field(ge=0, description="In the registry.")
    usable: int = Field(ge=0, description="With enough history in the panel.")
    candidate_pool: int = Field(ge=0, description="Unread candidates of the filing index.")
    controls: int = Field(ge=0, description="Firms without the action around the events.")
    support: Score | None = Field(default=None, description="Treated inside the controls' range.")
    balance: tuple[BalanceRow, ...] = ()
    leads: tuple[LeadRow, ...] = ()
    placebo: tuple[PlaceboRow, ...] = ()
    null: tuple[NullRow, ...] = ()
    synthetic: SyntheticFit | None = None
    confounded_share: Score = Field(description="Events whose document names another event.")
    near_decision_share: Score = Field(description="Events with another decision item nearby.")
    divisions: dict[str, int] = Field(description="Usable events per SIC division.")
    verdicts: tuple[MethodVerdict, ...] = Field(min_length=1)


class CausalStudy(ContractModel):
    """Labelled as what it is: a feasibility study, with no effect estimated."""

    study_id: Annotated[str, StringConstraints(pattern=r"^cst-[0-9]{8}-[0-9a-f]{12}$")]
    sha256: Sha256
    label: Literal["feasibility_study_no_effect_estimated"]
    effects_estimated: Literal[0]
    outcomes_after_treatment_read: Literal[False]
    data_cutoff: AwareDatetime
    dataset_id: str
    registry_version: str
    sample_id: str
    audit_credible: bool
    audit_blockers: tuple[Text, ...]
    graph: CausalGraph
    rules: tuple[Text, ...] = Field(description="What makes a method feasible, set beforehand.")
    treatments: tuple[TreatmentStudy, ...] = Field(min_length=1)
    findings: tuple[Text, ...]
    seed: int
    contracts_version: str
    created_at: AwareDatetime = Field(description="Not part of the hash.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.study_id.rsplit("-", 1)[1] != self.sha256[:12]:
            raise ValueError("the study is named by its SHA-256")
        return self
