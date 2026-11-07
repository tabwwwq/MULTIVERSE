"""Report Studio: a report replays byte for byte, and every number in it can be audited."""

import csv
import io
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from multiverse_simulation.cli import run_case
from multiverse_simulation.example import default_decision, illustrative_case
from multiverse_simulation.reportdoc import (
    FILES,
    build_document,
    cik_of,
    filing_url,
    render_files,
    replay,
    resolve,
    run_view,
    scale_of,
    write_report_files,
)
from pydantic import ValidationError

from multiverse_contracts.decisions import DECISION_MODELS, DecisionModel
from multiverse_contracts.primitives import DataOrigin
from multiverse_contracts.reports import (
    EMPIRICAL_LABEL,
    SYNTHETIC_LABEL,
    EvidenceLevel,
    ReportManifest,
    ResearchReport,
    SectionKey,
)
from multiverse_contracts.simulation import SimulationReport, SimulationSettings
from multiverse_contracts.source_catalog import SOURCE_CATALOG

CASE = illustrative_case(horizon=8, history_quarters=40)
CATALOG_IDS = {source.source_id for source in SOURCE_CATALOG.sources}
SETTINGS = SimulationSettings(paths=400, seed=11, batch_paths=200)
ROOT = Path(__file__).parents[3]


def decision(kind: str = "rnd_change") -> DecisionModel:
    return DECISION_MODELS[kind].model_validate_json(json.dumps(default_decision(kind)))  # type: ignore[return-value]


@pytest.fixture(scope="module")
def run() -> SimulationReport:
    return run_case(CASE, decision(), SETTINGS)


def test_a_report_replays_byte_for_byte_from_its_manifest(
    run: SimulationReport, tmp_path: Path
) -> None:
    manifest = write_report_files(tmp_path, run, CASE, decision())
    check = replay(manifest, tmp_path, CASE, run_case)
    assert check.identical
    assert [name for name, same in check.artifacts if same] == ["markdown", "csv", "document"]


def test_a_changed_file_fails_the_replay(run: SimulationReport, tmp_path: Path) -> None:
    manifest = write_report_files(tmp_path, run, CASE, decision())
    path = tmp_path / FILES["csv"]
    path.write_bytes(path.read_bytes().replace(b"p50", b"p51", 1))
    assert not replay(manifest, tmp_path, CASE, run_case).identical


def test_replay_refuses_another_case(run: SimulationReport, tmp_path: Path) -> None:
    manifest = write_report_files(tmp_path, run, CASE, decision())
    other = illustrative_case(horizon=8, history_quarters=40, seed=8)
    with pytest.raises(ValueError, match="is not the case"):
        replay(manifest, tmp_path, other, run_case)


def test_generation_is_idempotent(run: SimulationReport, tmp_path: Path) -> None:
    first = write_report_files(tmp_path, run, CASE, decision())
    stamps = {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    again = write_report_files(tmp_path, run, CASE, decision())
    assert first == again
    assert {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == stamps
    assert render_files(run, CASE, decision()).files == render_files(run, CASE, decision()).files


def test_the_identity_survives_a_new_clock_and_changes_with_the_run(run: SimulationReport) -> None:
    later = run.model_copy(
        update={"diagnostics": run.diagnostics.model_copy(update={"seconds": 9.9})}
    )
    assert build_document(later, CASE, decision()) == build_document(run, CASE, decision())
    other = run_case(CASE, decision(), SETTINGS.model_copy(update={"seed": 12}))
    assert (
        build_document(other, CASE, decision()).report_doc_id
        != build_document(run, CASE, decision()).report_doc_id
    )


def test_every_claim_can_be_audited(run: SimulationReport) -> None:
    document = build_document(run, CASE, decision())
    view = run_view(run, CASE, decision())
    assert len(document.claims) >= 10
    for claim in document.claims:
        assert str(resolve(view, claim.pointer)) == claim.value, claim.claim_id
    markdown = render_files(run, CASE, decision()).files[FILES["markdown"]].decode()
    for claim in document.claims:
        assert f"[{claim.claim_id}]" in markdown


def test_the_report_has_the_ten_sections_and_says_what_it_is(run: SimulationReport) -> None:
    document = build_document(run, CASE, decision())
    assert [s.key for s in document.sections] == list(SectionKey)
    assert document.evidence_level is EvidenceLevel.SYNTHETIC_DEMO
    assert document.label == SYNTHETIC_LABEL
    assert document.title.startswith("Synthetic demonstration.")
    markdown = render_files(run, CASE, decision()).files[FILES["markdown"]].decode()
    assert f"> **{SYNTHETIC_LABEL}.**" in markdown.splitlines()[2]
    causal = next(s for s in document.sections if s.key is SectionKey.CAUSAL)
    assert "No causal effect is estimated" in causal.paragraphs[0]


def test_a_synthetic_run_cannot_pose_as_market_truth(run: SimulationReport) -> None:
    document = build_document(run, CASE, decision())
    payload = json.loads(document.model_dump_json())
    for changes in (
        {"label": EMPIRICAL_LABEL},
        {"evidence_level": "conditional_simulation"},
        {"title": "Northwind Precision: a forecast"},
    ):
        with pytest.raises(ValidationError):
            ResearchReport.model_validate(payload | changes)
    real = payload | {"data_origin": DataOrigin.EMPIRICAL.value}
    with pytest.raises(ValidationError):
        ResearchReport.model_validate(real)


def test_the_csv_holds_the_numbers_of_the_run_in_full_units(run: SimulationReport) -> None:
    rows = list(
        csv.DictReader(
            io.StringIO(render_files(run, CASE, decision()).files["report.csv"].decode())
        )
    )
    revenue = next(m for m in run.result.metrics if m.metric.value == "revenue")
    point = revenue.forecasts[1].points[-1]
    found = {
        r["statistic"]: r["value"]
        for r in rows
        if r["table"] == "quantiles"
        and r["metric"] == "revenue"
        and r["scenario"] == "alt_a"
        and r["period"] == str(point.period_end)
    }
    assert found == {"p10": point.p10, "p50": point.p50, "p90": point.p90}
    ev = next(v for v in run.values if v.metric == "ev_change")
    assert {"table": "values", "metric": "ev_change", "statistic": "p50", "value": ev.p50} == {
        k: r[k]
        for r in rows
        if r["metric"] == "ev_change" and r["statistic"] == "p50"
        for k in ("table", "metric", "statistic", "value")
    }
    assert all(r["unit"] in {"USD", "share"} for r in rows)


def test_tables_state_their_unit_and_round_the_run(run: SimulationReport) -> None:
    document = build_document(run, CASE, decision())
    results = next(s for s in document.sections if s.key is SectionKey.RESULTS)
    values = next(t for t in results.tables if t.caption == "Model values at the cutoff")
    scale = scale_of(run)
    assert values.unit_note == scale.unit
    ev = next(v for v in run.values if v.metric == "enterprise_value" and v.scenario == "baseline")
    row = next(r for r in values.rows if r[0].startswith("Enterprise") and r[1] == "Baseline")
    assert row[3] == f"{Decimal(ev.p50 or '0') / scale.divisor:,.1f}"


def test_the_manifest_records_what_a_replay_needs(run: SimulationReport, tmp_path: Path) -> None:
    write_report_files(tmp_path, run, CASE, decision())
    manifest = ReportManifest.model_validate_json((tmp_path / "manifest.json").read_bytes())
    assert manifest.settings == SETTINGS
    assert manifest.case_id == CASE.case_id
    assert manifest.simulation_report_id == run.manifest.report_id
    assert {a.file for a in manifest.artifacts} == set(FILES.values())


def test_every_source_of_a_report_resolves(run: SimulationReport) -> None:
    document = build_document(run, CASE, decision())
    for ref in document.sources:
        if ref.kind.value == "method":
            assert (ROOT / ref.target).exists() or ref.target == "docs/adr/0034-report-studio.md"
        elif ref.kind.value == "run":
            assert ref.target == run.manifest.report_id
        elif ref.target.startswith("/data-catalog/"):
            assert ref.target.removeprefix("/data-catalog/") in CATALOG_IDS


def test_a_real_case_links_its_filings_by_cik() -> None:
    assert cik_of("case-48898-20251231") == "48898"
    assert cik_of("case-synthetic-northwind") is None
    url = filing_url("48898", "0000048898-25-000012")
    assert url == "https://www.sec.gov/Archives/edgar/data/48898/000004889825000012/"
    assert re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/\d+/\d{18}/", url)


def test_a_run_with_sensitivity_replays_with_it(tmp_path: Path) -> None:
    small = SETTINGS.model_copy(update={"paths": 200, "batch_paths": 100})
    report = run_case(CASE, decision(), small, True)
    assert len(report.sensitivity) == 5
    manifest = write_report_files(tmp_path, report, CASE, decision())
    assert manifest.sensitivity
    assert replay(manifest, tmp_path, CASE, run_case).identical
