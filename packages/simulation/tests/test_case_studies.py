"""The committed case studies of Stage 25: whole, honest, and every reference resolves.

The runs and cases live in ``var/``. Where they exist (on the machine that made them) the claims
are audited against the runs; everywhere else the files are checked against their manifests.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest
from multiverse_simulation.reportdoc import cik_of, resolve, run_view

from multiverse_contracts.decisions import DECISION_MODELS
from multiverse_contracts.reports import EMPIRICAL_LABEL, ReportManifest, ResearchReport
from multiverse_contracts.simulation import SimulationCase, SimulationReport
from multiverse_contracts.source_catalog import SOURCE_CATALOG

ROOT = Path(__file__).parents[3]
STUDIES = ROOT / "docs" / "case-studies"
RUNS = sorted(path.parent for path in STUDIES.glob("*/*/manifest.json"))
SEC = re.compile(r"^https://www\.sec\.gov/Archives/edgar/data/(\d+)/(\d{18})/$")
CATALOG = {source.source_id for source in SOURCE_CATALOG.sources}
DOCS = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "docs").rglob("*.md"))


def test_there_are_three_studies_of_two_runs() -> None:
    assert len(RUNS) == 6
    assert {run.parent.name for run in RUNS} == {
        "rnd-allocation",
        "ma-stress",
        "restructuring-exit",
    }


@pytest.mark.parametrize("run", RUNS, ids=lambda run: f"{run.parent.name}/{run.name}")
def test_the_files_are_those_the_manifest_hashed(run: Path) -> None:
    manifest = ReportManifest.model_validate_json((run / "manifest.json").read_bytes())
    for artifact in manifest.artifacts:
        data = (run / artifact.file).read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact.sha256, artifact.file
        assert len(data) == artifact.bytes
    decision = (run.parent / "decisions" / f"{run.name}.json").read_text(encoding="utf-8")
    parsed = DECISION_MODELS[json.loads(decision)["type"]].model_validate_json(decision)
    assert parsed == manifest.decision


@pytest.mark.parametrize("run", RUNS, ids=lambda run: f"{run.parent.name}/{run.name}")
def test_a_real_company_is_never_shown_as_more_than_a_conditional_model(run: Path) -> None:
    document = ResearchReport.model_validate_json((run / "document.json").read_bytes())
    assert document.label == EMPIRICAL_LABEL
    markdown = (run / "report.md").read_text(encoding="utf-8")
    assert f"> **{EMPIRICAL_LABEL}.**" in markdown
    assert "No causal effect is estimated" in markdown
    assert "not market" in markdown


@pytest.mark.parametrize("run", RUNS, ids=lambda run: f"{run.parent.name}/{run.name}")
def test_every_source_reference_resolves(run: Path) -> None:
    document = ResearchReport.model_validate_json((run / "document.json").read_bytes())
    manifest = ReportManifest.model_validate_json((run / "manifest.json").read_bytes())
    cik = cik_of(manifest.case_id)
    for ref in document.sources:
        target = ref.target
        if ref.kind.value == "sec_filing":
            found = SEC.match(target)
            assert found, target
            assert found.group(1) == cik
        elif ref.kind.value == "data_source":
            assert target.removeprefix("/data-catalog/") in CATALOG
        elif ref.kind.value == "method":
            assert (ROOT / target).is_file(), target
        elif ref.kind.value == "run":
            assert target == manifest.simulation_report_id
        else:
            assert target in DOCS, f"{target} is recorded in no document"
    cited = {source for claim in document.claims for source in claim.sources}
    assert cited <= {ref.ref_id for ref in document.sources}


@pytest.mark.parametrize("study", sorted(p for p in STUDIES.iterdir() if p.is_dir()))
def test_the_links_of_a_study_resolve(study: Path) -> None:
    text = (study / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)#]+)\)", text):
        if target.startswith("http"):
            continue
        assert (study / target).resolve().exists(), target


@pytest.mark.parametrize("run", RUNS, ids=lambda run: f"{run.parent.name}/{run.name}")
def test_every_claim_matches_the_run_where_the_run_exists(run: Path) -> None:
    manifest = ReportManifest.model_validate_json((run / "manifest.json").read_bytes())
    stored = ROOT / "var" / "data" / "case-studies" / run.parent.name / f"{run.name}.json"
    case_path = ROOT / "var" / "data" / "case-studies" / "cases" / f"{manifest.case_id}.json"
    if not stored.exists() or not case_path.exists():
        pytest.skip("the runs and cases of the studies live in var/ on the machine that made them")
    report = SimulationReport.model_validate_json(stored.read_bytes())
    case = SimulationCase.model_validate_json(case_path.read_bytes())
    view = run_view(report, case, manifest.decision)
    document = ResearchReport.model_validate_json((run / "document.json").read_bytes())
    for claim in document.claims:
        assert str(resolve(view, claim.pointer)) == claim.value, claim.claim_id


PUBLISHED_PAGES = sorted(
    [
        *(ROOT / "docs" / "portfolio").glob("*.md"),
        *(ROOT / "docs" / "releases").glob("*.md"),
        ROOT / "docs" / "governance" / "source-card.md",
        ROOT / "SUPPORT.md",
    ]
)


@pytest.mark.parametrize("page", PUBLISHED_PAGES, ids=lambda p: p.name)
def test_the_links_of_the_portfolio_resolve(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)#]+)\)", text):
        if target.startswith("http"):
            continue
        assert (page.parent / target).resolve().exists(), f"{page.name}: {target}"
