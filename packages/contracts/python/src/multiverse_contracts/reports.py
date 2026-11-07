"""Report Studio (Stage 25): a research report built from one finished run, and its manifest.

A report is derived from a simulation report, its case and its decision, and from nothing else:
no clock, no machine. The same inputs give the same bytes, so a manifest can replay a report and
compare it byte for byte. Its identity hashes the identity of the run, which already hashes the
case (with its dataset and model) and the decision: a new model or dataset makes a new report and
leaves the old one as it was.

Every number in the text is a claim with a JSON pointer into the run it came from, and every
claim names its sources. A reader can audit any sentence without trusting the renderer.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from multiverse_contracts.decisions import Decision
from multiverse_contracts.forecasting import Name
from multiverse_contracts.normalized import Text
from multiverse_contracts.pit import Sha256
from multiverse_contracts.primitives import ContractModel, DataOrigin
from multiverse_contracts.simulation import CaseId, ReportId, SimulationSettings

ResearchReportId = Annotated[str, StringConstraints(pattern=r"^rep-[0-9]{8}-[0-9a-f]{12}$")]
RefId = Annotated[str, StringConstraints(pattern=r"^S[0-9]{1,3}$")]
ClaimId = Annotated[str, StringConstraints(pattern=r"^C[0-9]{1,3}$")]

GENERATOR_VERSION = "report-studio-1"
EMPIRICAL_LABEL = (
    "Conditional on the assumed model, not validated: model values, not market values, "
    "and no causal effect"
)
SYNTHETIC_LABEL = "Synthetic demonstration: invented company and figures, not a real result"


class EvidenceLevel(StrEnum):
    """How far the numbers of a report can be trusted, in words a reader can check."""

    CONDITIONAL_SIMULATION = "conditional_simulation"
    SYNTHETIC_DEMO = "synthetic_demo"


class SourceKind(StrEnum):
    SEC_FILING = "sec_filing"
    DATA_SOURCE = "data_source"
    DATASET = "dataset"
    MODEL = "model"
    METHOD = "method"
    RUN = "run"


class SectionKey(StrEnum):
    """The parts every report has, in this order (prompt 25)."""

    OBJECTIVE = "objective"
    CUTOFF = "cutoff"
    SOURCES = "sources"
    ACTION = "action"
    MODELS = "models"
    RESULTS = "results"
    CAUSAL = "causal"
    ASSUMPTIONS = "assumptions"
    SENSITIVITY = "sensitivity"
    LIMITATIONS = "limitations"


ClaimUnit = Literal["usd", "share", "quarters", "paths", "count", "date", "text"]


class SourceRef(ContractModel):
    """Where a statement comes from: a filing, a source, a dataset, a model or a document."""

    ref_id: RefId
    kind: SourceKind
    label: Text
    target: str = Field(
        min_length=1,
        max_length=300,
        description="An https URL, a path in this repository, or an id that one of them records.",
    )
    record: str | None = Field(
        default=None,
        max_length=200,
        description="For a dataset, model or run: the repository file that records the id.",
    )


class ReportClaim(ContractModel):
    """One number of the text, and how to find it again in the run."""

    claim_id: ClaimId
    statement: Text
    value: str = Field(min_length=1, max_length=80)
    unit: ClaimUnit
    pointer: str = Field(
        pattern=r"^/(report|case|decision)(/[A-Za-z0-9_.-]+)*$",
        description="JSON pointer into {report, case, decision} of the run.",
    )
    sources: tuple[RefId, ...] = Field(min_length=1)


class ReportTable(ContractModel):
    caption: Text
    columns: tuple[str, ...] = Field(min_length=1)
    rows: tuple[tuple[str, ...], ...]
    unit_note: Text | None = None

    @model_validator(mode="after")
    def _rectangular(self) -> Self:
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError(f"{self.caption}: every row has one cell per column")
        return self


class ReportSection(ContractModel):
    key: SectionKey
    title: str = Field(min_length=1, max_length=80)
    paragraphs: tuple[str, ...] = Field(min_length=1)
    tables: tuple[ReportTable, ...] = ()


class ResearchReport(ContractModel):
    """The document: what a reader sees, in Markdown, CSV, print or on screen."""

    contracts_version: str
    generator_version: str
    report_doc_id: ResearchReportId
    simulation_report_id: ReportId
    title: str = Field(min_length=1, max_length=160)
    company_id: str
    company_name: str = Field(min_length=1)
    as_of: date
    data_origin: DataOrigin
    evidence_level: EvidenceLevel
    label: str = Field(min_length=1)
    sections: tuple[ReportSection, ...]
    claims: tuple[ReportClaim, ...] = Field(min_length=1)
    sources: tuple[SourceRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _complete_and_honest(self) -> Self:
        if tuple(section.key for section in self.sections) != tuple(SectionKey):
            raise ValueError("a report has the ten sections of prompt 25, in order")
        known = {ref.ref_id for ref in self.sources}
        for claim in self.claims:
            missing = set(claim.sources) - known
            if missing:
                raise ValueError(f"{claim.claim_id} cites unknown sources {sorted(missing)}")
        if len({claim.claim_id for claim in self.claims}) != len(self.claims):
            raise ValueError("claim ids are unique")
        synthetic = self.data_origin is DataOrigin.SYNTHETIC
        if synthetic != (self.evidence_level is EvidenceLevel.SYNTHETIC_DEMO):
            raise ValueError("a synthetic run is a synthetic demonstration, and only it is")
        if self.label != (SYNTHETIC_LABEL if synthetic else EMPIRICAL_LABEL):
            raise ValueError("the label says what the numbers are (SYN-01, SIM-03)")
        if synthetic and "Synthetic" not in self.title:
            raise ValueError("the title of a synthetic report says so")
        return self


ArtifactFormat = Literal["markdown", "csv", "document"]


class ReportArtifact(ContractModel):
    format: ArtifactFormat
    file: str = Field(pattern=r"^[a-z0-9.-]+\.(md|csv|json)$")
    sha256: Sha256
    bytes: int = Field(ge=1)


class ReportManifest(ContractModel):
    """Enough to build the report again and to prove it is the same, byte for byte."""

    report_doc_id: ResearchReportId
    generator_version: str
    contracts_version: str
    simulation_report_id: ReportId
    case_id: CaseId
    case_sha256: Sha256
    decision: Decision = Field(description="The decision itself: small, and needed to replay.")
    decision_sha256: Sha256
    settings: SimulationSettings
    sensitivity: bool = Field(
        default=False, description="The run also ran the sensitivity variants of the shock model."
    )
    dataset_id: str | None = None
    dataset_sha256: Sha256 | None = None
    model_id: str | None = None
    finance_version: str
    simulation_version: str
    artifacts: tuple[ReportArtifact, ...] = Field(min_length=3, max_length=3)


class ReplayCheck(ContractModel):
    """The outcome of building a report again from its manifest."""

    report_doc_id: ResearchReportId
    artifacts: tuple[tuple[Name, bool], ...]
    identical: bool
