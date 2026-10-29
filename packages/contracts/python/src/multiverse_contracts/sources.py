"""Source catalog: official data sources, terms, risks and the acquisition plan (docs/04, docs/12).

The catalog holds metadata only. It says where data would come from, under which terms,
how fast it may be requested and how revisions work, but it contains no data, and no
download may start for a source until the owner approves it (``DownloadDecision``).

Free access is not a licence. Access category, API key, redistribution and resale are
separate fields, and resale stays "not granted" unless a licence explicitly allows it.

``python -m multiverse_contracts.source_catalog`` writes the catalog to
``catalog/sources.json``; it is what ``GET /api/v1/sources`` will return.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, StringConstraints, model_validator

from multiverse_contracts.interventions import InterventionType
from multiverse_contracts.primitives import ContractModel, DecimalString

Slug = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64),
    Field(description="Lowercase identifier with dashes, for example 'sec-edgar'."),
]
HttpsUrl = Annotated[
    str,
    StringConstraints(pattern=r"^https://[a-z0-9.-]+(/\S*)?$", max_length=500),
    Field(description="Absolute HTTPS address without credentials or port."),
]
Text = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
Cik = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{10}$"),
    Field(description="SEC Central Index Key, zero-padded to 10 digits."),
]


class AccessCategory(StrEnum):
    """How a source is reached. A free endpoint is still not a licence (docs/12)."""

    PUBLIC_ACCESS = "public_access"
    API_KEY = "api_key"
    LICENSED = "licensed"


class Authentication(StrEnum):
    NONE = "none"
    DECLARED_USER_AGENT = "declared_user_agent"
    API_KEY = "api_key"
    CONTRACT = "contract"


class KeyStatus(StrEnum):
    """Whether a key is needed and who has to obtain it."""

    NOT_REQUIRED = "not_required"
    OWNER_MUST_REGISTER = "owner_must_register"
    CONTRACT_REQUIRED = "contract_required"


class Redistribution(StrEnum):
    """What the terms say about passing the data on."""

    PUBLIC_INFORMATION = "public_information"
    OPEN_LICENCE = "open_licence"
    REUSE_WITH_CONDITIONS = "reuse_with_conditions"
    PERMISSION_REQUIRED = "permission_required"
    NOT_ALLOWED = "not_allowed"


class Resale(StrEnum):
    """Selling the data itself. Not granted unless a licence says so explicitly."""

    NOT_GRANTED = "not_granted"
    ALLOWED_BY_LICENCE = "allowed_by_licence"
    PROHIBITED = "prohibited"


class DocKind(StrEnum):
    API_REFERENCE = "api_reference"
    ACCESS_POLICY = "access_policy"
    TERMS = "terms"
    DATASET_PAGE = "dataset_page"
    DOCUMENTATION = "documentation"


class DataFormat(StrEnum):
    JSON = "json"
    CSV = "csv"
    XML = "xml"
    SDMX_ML = "sdmx_ml"
    TSV = "tsv"
    ZIP = "zip"
    XLSX = "xlsx"
    JSON_STAT = "json_stat"
    HTML = "html"


class FieldType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    DATETIME = "datetime"
    CODE = "code"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


class FieldRole(StrEnum):
    """What a field means for point-in-time use (docs/04)."""

    IDENTIFIER = "identifier"
    PERIOD = "period"
    KNOWLEDGE_TIME = "knowledge_time"
    VALUE = "value"
    UNIT = "unit"
    REVISION = "revision"
    METADATA = "metadata"


class DecisionStatus(StrEnum):
    AWAITING_OWNER = "awaiting_owner_decision"
    APPROVED = "approved"
    DECLINED = "declined"


class DownloadScope(StrEnum):
    """What an approval covers: a named sample through the API, or bulk files as well."""

    SAMPLE = "sample"
    BULK = "bulk"


class Level(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskCategory(StrEnum):
    REGION_AND_GAAP = "region_and_gaap"
    SURVIVORSHIP = "survivorship"
    MISSING_TAGS = "missing_tags"
    QUARTERIZATION = "quarterization"
    RESTATEMENT = "restatement"
    TIME_TO_PUBLICATION = "time_to_publication"
    CURRENCY_AND_SCALE = "currency_and_scale"
    IDENTIFIERS = "identifiers"
    TERMS_OF_USE = "terms_of_use"
    ACCESS = "access"
    DATA_ERRORS = "data_errors"
    REVISIONS = "revisions"
    VOLUME = "volume"


class Evidence(StrEnum):
    """Whether a score rests on a checked fact or on an expectation still to be checked."""

    VERIFIED = "verified"
    EXPECTED = "expected"


class DocLink(ContractModel):
    title: Text
    url: HttpsUrl
    kind: DocKind


class Licence(ContractModel):
    name: Text
    summary: Text
    redistribution: Redistribution
    resale: Resale
    attribution: Text | None = Field(default=None, description="Wording the terms ask for.")
    exceptions: Text | None = Field(
        default=None, description="Parts of the source the general terms do not cover."
    )


class RateLimit(ContractModel):
    """What the provider documents, and the slower rate MULTIVERSE will use."""

    documented: Text
    documented_requests_per_second: DecimalString | None = None
    chosen_requests_per_second: DecimalString

    @model_validator(mode="after")
    def _chosen_within_documented(self) -> Self:
        chosen = Decimal(self.chosen_requests_per_second)
        if chosen <= 0:
            raise ValueError("the chosen request rate must be positive")
        limit = self.documented_requests_per_second
        if limit is not None and chosen > Decimal(limit):
            raise ValueError("the chosen request rate must not exceed the documented limit")
        return self


class DictionaryField(ContractModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    type: FieldType
    role: FieldRole
    description: Text


class Dataset(ContractModel):
    """One product of a source, with its data dictionary and revision behaviour."""

    dataset_id: Slug
    title: Text
    description: Text
    endpoints: tuple[Annotated[str, StringConstraints(pattern=r"^https://\S+$")], ...] = Field(
        min_length=1, description="URL patterns; placeholders such as {cik} are not real values."
    )
    formats: tuple[DataFormat, ...] = Field(min_length=1)
    update_frequency: Text
    knowledge_time: Text = Field(description="How to tell when a value became public.")
    revision_semantics: Text
    coverage: Text
    identifiers: tuple[Text, ...] = Field(min_length=1)
    provenance: tuple[Text, ...] = Field(
        min_length=1, description="What is recorded with every raw file."
    )
    fields: tuple[DictionaryField, ...] = Field(min_length=1)
    size: Text | None = None
    docs: tuple[DocLink, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_fields(self) -> Self:
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate field names in {self.dataset_id}")
        return self


class DownloadDecision(ContractModel):
    """The owner's decision about automatic downloads from a source."""

    status: DecisionStatus
    decided_on: date | None = None
    scope: DownloadScope | None = Field(
        default=None, description="What the approval covers; set exactly when approved."
    )
    note: Text

    @model_validator(mode="after")
    def _dated_when_decided(self) -> Self:
        if (self.status is DecisionStatus.AWAITING_OWNER) != (self.decided_on is None):
            raise ValueError("a decision has a date exactly when it is no longer awaited")
        if (self.status is DecisionStatus.APPROVED) != (self.scope is not None):
            raise ValueError("an approval states its scope, and only an approval has one")
        return self


class DataSource(ContractModel):
    source_id: Slug
    name: Text
    publisher: Text
    region: Text
    priority: int = Field(ge=1, le=6, description="Source-of-truth order of docs/04.")
    access: AccessCategory
    authentication: Authentication
    key_status: KeyStatus
    licence: Licence
    rate_limit: RateLimit
    request_rules: tuple[Text, ...] = Field(min_length=1)
    retry_policy: Text
    checksum_policy: Text
    official_hosts: tuple[Annotated[str, StringConstraints(pattern=r"^[a-z0-9.-]+$")], ...] = Field(
        min_length=1
    )
    docs: tuple[DocLink, ...] = Field(min_length=2)
    datasets: tuple[Dataset, ...] = Field(min_length=1)
    verified_on: date
    download: DownloadDecision
    notes: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        hosts = set(self.official_hosts)
        links = [*self.docs, *(doc for dataset in self.datasets for doc in dataset.docs)]
        for link in links:
            if urlsplit(link.url).hostname not in hosts:
                raise ValueError(f"{link.url} is not on an official host of {self.source_id}")
        kinds = {link.kind for link in self.docs}
        if not kinds & {DocKind.API_REFERENCE, DocKind.DOCUMENTATION}:
            raise ValueError(f"{self.source_id} needs its primary technical documentation")
        if not kinds & {DocKind.TERMS, DocKind.ACCESS_POLICY}:
            raise ValueError(f"{self.source_id} needs its terms or access policy")

        expected = {
            AccessCategory.PUBLIC_ACCESS: (
                {Authentication.NONE, Authentication.DECLARED_USER_AGENT},
                KeyStatus.NOT_REQUIRED,
            ),
            AccessCategory.API_KEY: ({Authentication.API_KEY}, KeyStatus.OWNER_MUST_REGISTER),
            AccessCategory.LICENSED: ({Authentication.CONTRACT}, KeyStatus.CONTRACT_REQUIRED),
        }[self.access]
        if self.authentication not in expected[0] or self.key_status is not expected[1]:
            raise ValueError(f"{self.source_id}: access, authentication and key status disagree")

        # A free endpoint is not a resale licence: only an explicit licence can allow resale.
        if self.licence.resale is Resale.ALLOWED_BY_LICENCE and self.licence.redistribution not in {
            Redistribution.OPEN_LICENCE,
            Redistribution.REUSE_WITH_CONDITIONS,
        }:
            raise ValueError(f"{self.source_id}: resale needs an explicit licence")
        if self.access is AccessCategory.LICENSED and self.licence.resale is not Resale.PROHIBITED:
            raise ValueError(f"{self.source_id}: licensed data is never resold")

        dataset_ids = [dataset.dataset_id for dataset in self.datasets]
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError(f"duplicate dataset IDs in {self.source_id}")
        return self


class LicensedNeed(ContractModel):
    """Data that only a licensed provider can supply. No provider is chosen in V2."""

    need_id: Slug
    title: Text
    why: Text
    without_it: Text = Field(description="What the platform does while the data is missing.")
    requirement: Text
    earliest_version: Literal["V2", "V3", "V4"]
    status: Literal["not_selected"]


class Risk(ContractModel):
    risk_id: Annotated[str, StringConstraints(pattern=r"^R-[0-9]{2}$")]
    title: Text
    category: RiskCategory
    description: Text
    sources: tuple[Slug, ...] = Field(min_length=1)
    likelihood: Level
    impact: Level
    mitigation: Text
    detection: Text = Field(description="The check or test that shows the risk materialised.")
    stage: int = Field(ge=9, le=26, description="Stage that implements the mitigation.")


class SectorPriority(ContractModel):
    sector: Text
    sic_codes: tuple[Annotated[str, StringConstraints(pattern=r"^[0-9]{4}(-[0-9]{4})?$")], ...] = (
        Field(min_length=1)
    )
    priority: Literal["p1", "p2", "p3", "excluded"]
    rationale: Text
    decisions: tuple[InterventionType, ...] = ()


class Criterion(ContractModel):
    criterion_id: Annotated[str, StringConstraints(pattern=r"^C[0-9]$")]
    title: Text
    weight: int = Field(ge=1, le=3)
    how_checked: Text


class Score(ContractModel):
    criterion_id: Annotated[str, StringConstraints(pattern=r"^C[0-9]$")]
    points: int = Field(ge=0, le=2)
    evidence: Evidence
    basis: Text


class CompanyCandidate(ContractModel):
    """A real company proposed for the first acquisition. Only the verified fields are facts."""

    rank: int = Field(ge=1, le=10)
    name: Text
    cik: Cik
    ticker: Annotated[str, StringConstraints(pattern=r"^[A-Z.]{1,6}$")] | None
    sic: Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")]
    sic_description: Text
    sector_priority: Literal["p1", "p2", "p3"]
    fiscal_year_end: Annotated[str, StringConstraints(pattern=r"^(0[1-9]|1[0-2])[0-3][0-9]$")]
    filer_category: Text
    status: Literal["listed", "acquired"]
    verified_on: date
    decisions: tuple[InterventionType, ...] = Field(min_length=1)
    scores: tuple[Score, ...] = Field(min_length=1)
    total: int = Field(ge=0)
    concerns: tuple[Text, ...] = ()


class AcquisitionStep(ContractModel):
    step: int = Field(ge=1)
    title: Text
    sources: tuple[Slug, ...] = Field(min_length=1)
    scope: Text
    volume: Text
    storage: Text
    checks: tuple[Text, ...] = Field(min_length=1)
    owner_decision: Text | None = Field(
        default=None, description="What the owner has to decide before this step may run."
    )
    decided_on: date | None = Field(
        default=None, description="When the owner took that decision; empty while it is open."
    )
    stage: int = Field(ge=9, le=26)

    @model_validator(mode="after")
    def _decided_only_if_asked(self) -> Self:
        if self.decided_on is not None and self.owner_decision is None:
            raise ValueError("only a step that needs an owner decision can record one")
        return self


class SourceCatalog(ContractModel):
    """Every source, risk and planned step, checked as one document."""

    contracts_version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
    verified_on: date
    automatic_downloads: Literal["disabled"] = Field(
        description=(
            "Nothing is scheduled: downloads run only as explicit commands, and only from a "
            "source the owner approved."
        )
    )
    sources: tuple[DataSource, ...] = Field(min_length=1)
    licensed_needs: tuple[LicensedNeed, ...] = ()
    risks: tuple[Risk, ...] = Field(min_length=1)
    sectors: tuple[SectorPriority, ...] = Field(min_length=1)
    rubric: tuple[Criterion, ...] = Field(min_length=1)
    candidates: tuple[CompanyCandidate, ...] = Field(max_length=10)
    acquisition_plan: tuple[AcquisitionStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source IDs")
        known = set(source_ids)
        for risk in self.risks:
            if unknown := set(risk.sources) - known:
                raise ValueError(f"{risk.risk_id} names unknown sources: {sorted(unknown)}")
        for step in self.acquisition_plan:
            if unknown := set(step.sources) - known:
                raise ValueError(f"step {step.step} names unknown sources: {sorted(unknown)}")
        risk_ids = [risk.risk_id for risk in self.risks]
        if len(risk_ids) != len(set(risk_ids)):
            raise ValueError("duplicate risk IDs")
        if [step.step for step in self.acquisition_plan] != list(
            range(1, len(self.acquisition_plan) + 1)
        ):
            raise ValueError("acquisition steps are numbered 1, 2, 3 and so on")

        weights = {criterion.criterion_id: criterion.weight for criterion in self.rubric}
        if len(weights) != len(self.rubric):
            raise ValueError("duplicate rubric criteria")
        if [candidate.rank for candidate in self.candidates] != list(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("candidates are ranked 1, 2, 3 and so on")
        ciks = [candidate.cik for candidate in self.candidates]
        if len(ciks) != len(set(ciks)):
            raise ValueError("duplicate candidate CIKs")
        totals = []
        for candidate in self.candidates:
            scored = [score.criterion_id for score in candidate.scores]
            if sorted(scored) != sorted(weights):
                raise ValueError(f"{candidate.name} must be scored once on every criterion")
            total = sum(weights[score.criterion_id] * score.points for score in candidate.scores)
            if total != candidate.total:
                raise ValueError(f"{candidate.name}: total {candidate.total} should be {total}")
            totals.append(total)
        if totals != sorted(totals, reverse=True):
            raise ValueError("candidates are ranked by their total score")
        return self
