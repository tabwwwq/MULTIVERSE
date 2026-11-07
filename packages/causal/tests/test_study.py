"""The causal study on invented panels, and the real file: blind, gated and honest."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest

from multiverse_causal.design import GRAPH, RULES
from multiverse_causal.diagnostics import (
    CORE,
    LEADS,
    SHIFTS,
    Treated,
    e_value,
    excluded_mask,
    logistic,
    match,
    null_rows,
    placebo_dates,
    pre_trends,
    simplex_weights,
    support_and_balance,
    synthetic_fit,
    usable_events,
)
from multiverse_causal.estimators import (
    CausalWorkBlockedError,
    difference_in_differences,
    require_open_gate,
)
from multiverse_causal.panel import COVARIATES, OUTCOMES, Panel, load_panel, quarter_of
from multiverse_causal.study import read_index, verdicts
from multiverse_contracts.causal import (
    BalanceRow,
    CausalStudy,
    LeadRow,
    MethodVerdict,
    NullRow,
    PlaceboRow,
    SyntheticFit,
    TreatmentStudy,
)
from multiverse_contracts.events import EventType, QualityAudit

ROOT = Path(__file__).parents[3]


def panel(firms: int = 60, quarters: int = 40, seed: int = 3) -> Panel:
    """Firms with persistent noise and no effect of anything."""
    rng = np.random.default_rng(seed)
    outcomes = rng.normal(0, 0.1, size=(firms, quarters, len(OUTCOMES)))
    covariates = rng.normal(0, 1, size=(firms, quarters, len(COVARIATES)))
    covariates[:, :, -1][rng.random((firms, quarters)) < 0.5] = np.nan  # debt is often missing
    divisions = tuple("D" if i % 2 else "I" for i in range(firms))
    ciks = tuple(f"{i + 1:010d}" for i in range(firms))
    return Panel(ciks, divisions, 2010 * 4, outcomes, covariates)


def audit(credible: bool = False) -> QualityAudit:
    return QualityAudit(
        registry_version="0.1.0",
        sample_id="evs-20261106-abababababab",
        candidates_read=1,
        events=1,
        rejected=0,
        by_type=(),
        by_completion=(),
        by_division=(),
        deregistered_events=0,
        human_reviewed=0,
        double_reviewed=0,
        unknown_rate=(),
        confounded=0,
        overlap=(),
        overlap_window_days=365,
        credible_for_causal_work=credible,
        blockers=() if credible else ("0 of 1 events have a human review",),
        contracts_version="0.23.0",
    )


def no_exclusions(data: Panel) -> np.ndarray:
    return np.zeros((len(data.ciks), data.quarters), dtype=bool)


EVENTS = [Treated(i, 25 + i % 5) for i in range(10)]


def poisoned(data: Panel, events: list[Treated]) -> Panel:
    """The same panel with every treated value from the event quarter on replaced."""
    outcomes = data.outcomes.copy()
    covariates = data.covariates.copy()
    for e in events:
        outcomes[e.firm, e.event :] = 1e6
        covariates[e.firm, e.event :] = 1e6
    return replace(data, outcomes=outcomes, covariates=covariates)


def test_no_diagnostic_reads_a_treated_outcome_after_the_event() -> None:
    data = panel()
    other = poisoned(data, EVENTS)
    excluded = excluded_mask(data, {}, 8, EVENTS)
    assert pre_trends(data, EVENTS, excluded) == pre_trends(other, EVENTS, excluded)
    assert placebo_dates(data, EVENTS, excluded) == placebo_dates(other, EVENTS, excluded)
    assert support_and_balance(data, EVENTS, excluded) == support_and_balance(
        other, EVENTS, excluded
    )
    assert synthetic_fit(data, EVENTS, excluded) == synthetic_fit(other, EVENTS, excluded)
    assert null_rows(data, excluded, 10, 100, 1) == null_rows(other, excluded, 10, 100, 1)
    assert usable_events(data, EVENTS) == usable_events(other, EVENTS)


def test_leads_and_placebo_dates_stay_before_the_event() -> None:
    assert max(LEADS) <= -2
    assert min(SHIFTS) >= 4  # a window of four quarters ends at the event at the latest


def test_a_match_keeps_the_division_and_avoids_firms_near_the_action() -> None:
    data = panel()
    free = no_exclusions(data)
    partner = match(data, 1, 20, free)
    assert partner is not None
    assert data.divisions[partner] == data.divisions[1]
    assert partner != 1
    blocked = free.copy()
    blocked[partner, 20] = True
    assert match(data, 1, 20, blocked) != partner
    hole = data.covariates.copy()
    hole[1, 20, :CORE] = np.nan
    assert match(replace(data, covariates=hole), 1, 20, free) is None


def test_exclusions_cover_the_margin_and_a_treated_firm_leaves_for_good() -> None:
    data = panel(firms=3, quarters=20)
    mask = excluded_mask(data, {1: [10]}, 3)
    assert mask[1, 7:14].all()
    assert not mask[1, 6]
    assert not mask[1, 14]
    assert not mask[0].any()
    gone = excluded_mask(data, {}, 3, [Treated(2, 10)])
    assert gone[2, 7:].all()
    assert not gone[2, 6]


def test_support_sees_treated_firms_nobody_resembles() -> None:
    data = panel()
    covariates = data.covariates.copy()
    for e in EVENTS:
        covariates[e.firm, e.event - 1, :CORE] = 25.0
    far = replace(data, covariates=covariates)
    excluded = excluded_mask(far, {}, 8, EVENTS)
    share, rows = support_and_balance(far, EVENTS, excluded)
    assert share is not None
    assert share < 0.5
    assert rows[0].before > 1
    close, _ = support_and_balance(data, EVENTS, excluded)
    assert close is not None
    assert close >= 0.7


def test_logistic_scores_separate_what_differs() -> None:
    rng = np.random.default_rng(1)
    x = np.r_[rng.normal(-2, 1, (50, 1)), rng.normal(2, 1, (50, 1))]
    y = np.r_[np.zeros(50), np.ones(50)]
    scores = logistic(x, y)
    assert scores[y == 1].mean() > 0.8
    assert scores[y == 0].mean() < 0.2


def test_chance_is_measured_and_shrinks_with_more_events() -> None:
    data = panel(firms=80)
    excluded = no_exclusions(data)
    few = null_rows(data, excluded, 10, 100, 1)
    many = null_rows(data, excluded, 40, 100, 1)
    assert [r.outcome for r in few] == list(OUTCOMES)
    assert few[0].minimum_effect_now > many[0].minimum_effect_now
    assert few[0].minimum_effect_pool < few[0].minimum_effect_now
    assert 0 <= few[0].false_positive_rate < 0.15
    assert few[0].e_value > 1


def test_an_e_value_grows_with_the_effect() -> None:
    assert e_value(0.0) == pytest.approx(1.0)
    assert e_value(1.0) > e_value(0.5) > 1


def test_synthetic_weights_are_a_convex_mix() -> None:
    rng = np.random.default_rng(2)
    donors = rng.normal(size=(8, 30))
    target = donors[:, :3].mean(axis=1)
    weights = simplex_weights(donors, target)
    assert weights.min() >= 0
    assert weights.sum() == pytest.approx(1)
    assert np.abs(donors @ weights - target).max() < 0.2


def test_an_effect_cannot_be_estimated_before_the_audit_opens() -> None:
    data = panel()
    with pytest.raises(CausalWorkBlockedError, match="human review"):
        require_open_gate(audit())
    with pytest.raises(CausalWorkBlockedError):
        difference_in_differences(
            audit(), data, EVENTS, no_exclusions(data), 0, ("x", "y", "z"), (), ()
        )


def test_the_estimator_finds_an_invented_effect_and_carries_its_metadata() -> None:
    data = panel(firms=120, seed=9)
    events = [Treated(i, 25) for i in range(40)]
    outcomes = data.outcomes.copy()
    for e in events:
        outcomes[e.firm, e.event :, 0] += 0.5  # invented: a known jump
    jumped = replace(data, outcomes=outcomes)
    excluded = excluded_mask(jumped, {e.firm: [e.event] for e in events}, 8)
    found = difference_in_differences(
        audit(credible=True),
        jumped,
        events,
        excluded,
        0,
        ("rev_growth_l1", "2026-10-28", "invented cohort"),
        ("macro",),
        ("expectations",),
    )
    assert found.effect == pytest.approx(0.5, abs=0.1)
    assert found.standard_error > 0
    assert found.events == 40
    assert found.data_cutoff == "2026-10-28"
    assert found.untested_assumptions == ("expectations",)


def study(usable: int = 40) -> TreatmentStudy:
    return TreatmentStudy(
        treatment=EventType.LAYOFF,
        estimand="x",
        assumptions=("y",),
        untested=("z",),
        events=usable,
        usable=usable,
        candidate_pool=100,
        controls=100,
        support=0.95,
        balance=(BalanceRow(covariate="log_rev_ttm", before=0.5, after=0.1),),
        leads=(LeadRow(outcome="op_margin_l1", lead=-3, mean=0, low=-1, high=1, events=9),),
        placebo=(
            PlaceboRow(outcome="op_margin_l1", shift=6, estimate=0, low=-1, high=1, events=9),
        ),
        null=(
            NullRow(
                outcome="op_margin_l1",
                draws=10,
                pseudo_events=9,
                spread=0.1,
                false_positive_rate=0.05,
                minimum_effect_now=0.1,
                minimum_effect_pool=0.05,
                e_value=2,
            ),
        ),
        synthetic=SyntheticFit(usable=usable, median_donors=30, median_holdout_ratio=1.2),
        confounded_share=0,
        near_decision_share=0,
        divisions={"D": usable},
        verdicts=(MethodVerdict(method="matched_cohort", feasible=False, reasons=("x",)),),
    )


def test_the_audit_alone_closes_every_method() -> None:
    assert all(v.feasible for v in verdicts(study(), audit(credible=True)))
    closed = verdicts(study(), audit())
    assert not any(v.feasible for v in closed)
    assert all("not credible" in v.reasons[0] for v in closed)


def test_each_rule_can_fail_by_itself() -> None:
    open_audit = audit(credible=True)
    few = {v.method: v.feasible for v in verdicts(study(usable=5), open_audit)}
    assert not few["matched_cohort"]
    assert not few["did_event_study"]
    trending = study().model_copy(
        update={
            "leads": (
                LeadRow(outcome="op_margin_l1", lead=-3, mean=1, low=0.5, high=1.5, events=9),
                LeadRow(outcome="op_margin_l1", lead=-4, mean=1, low=0.5, high=1.5, events=9),
            )
        }
    )
    verdict = {v.method: v for v in verdicts(trending, open_audit)}
    assert not verdict["did_event_study"].feasible
    assert verdict["matched_cohort"].feasible


def test_the_graph_says_what_nobody_can_see() -> None:
    hidden = [n for n in GRAPH.nodes if not n.observed]
    assert "expectations" in {n.node_id for n in hidden}
    pairs = {(e.source, e.target) for e in GRAPH.edges}
    assert {("expectations", "action"), ("expectations", "outcome")} <= pairs
    assert GRAPH.omitted
    assert any(rule.startswith("Audit") for rule in RULES)


def test_the_panel_reads_quarters_and_scales_ratios(tmp_path: Path) -> None:
    columns = ["cik", "origin", "division", *sorted({*OUTCOMES, *COVARIATES})]
    rows = [",".join(columns)]
    for origin, margin in (("2012-03-31", "10"), ("2012-06-30", "")):
        values = {"cik": "0000000001", "origin": origin, "division": "D", "op_margin_l1": margin}
        rows.append(",".join(values.get(c, "0.1") for c in columns))
    path = tmp_path / "dataset.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    data = load_panel(path)
    assert data.first == quarter_of(date(2012, 3, 31))
    assert data.quarters == 2
    margin = OUTCOMES.index("op_margin_l1")
    assert data.outcomes[0, 0, margin] == pytest.approx(np.arcsinh(100))
    assert np.isnan(data.outcomes[0, 1, margin])


def test_the_index_is_read_per_company(tmp_path: Path) -> None:
    path = tmp_path / "decisions.csv"
    path.write_text("cik,filed_on,item\n0000000001,2020-03-01,2.03\n", encoding="utf-8")
    assert read_index(path)["0000000001"] == [(date(2020, 3, 1), "2.03")]


def test_the_real_study_estimates_nothing_and_says_why() -> None:
    real = CausalStudy.model_validate_json((ROOT / "data/causal/study.json").read_bytes())
    assert real.effects_estimated == 0
    assert real.outcomes_after_treatment_read is False
    assert real.label == "feasibility_study_no_effect_estimated"
    assert not real.audit_credible
    assert {t.treatment for t in real.treatments} == set(EventType)
    for treatment in real.treatments:
        assert treatment.untested
        assert all(not v.feasible and v.reasons for v in treatment.verdicts)
    assert real.data_cutoff < datetime(2026, 11, 7, tzinfo=UTC)
