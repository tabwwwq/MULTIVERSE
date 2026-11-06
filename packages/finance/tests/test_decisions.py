"""A decision of the contract reaches the engine with the meaning the form gave it."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from multiverse_contracts.decisions import DECISION_MODELS, DecisionModel
from multiverse_contracts.interventions import CATALOG, InterventionSpec
from multiverse_finance.decisions import plan_for, quarter_of
from multiverse_finance.engine import project
from multiverse_finance.exact import FinanceError
from multiverse_finance.example import illustrative_baseline
from multiverse_finance.model import Tranche

D = Decimal
MILLION = D(1_000_000)
BASE = illustrative_baseline(20, unit=MILLION)
SAME_RATE = replace(
    BASE,
    opening=replace(
        BASE.opening,
        tranches=(Tranche("notes", 1500 * MILLION, D("0.06")),),
    ),
)


def default_decision(spec: InterventionSpec, **changes: object) -> DecisionModel:
    """The documented defaults of the catalog, effective a quarter after the base date."""
    unit = spec.magnitude.default_unit or spec.magnitude.units[0].unit
    unit_spec = next(u for u in spec.magnitude.units if u.unit == unit)
    decision: dict[str, Any] = {
        "type": spec.type.value,
        "magnitude": {"value": unit_spec.default_value, "unit": unit.value},
        "timing": {
            "announcement_date": "2026-07-01",
            "effective_date": "2026-10-01",
            "lag_quarters": int(spec.lag_quarters.default),  # type: ignore[arg-type]
            "ramp_quarters": int(spec.ramp_quarters.default),  # type: ignore[arg-type]
        },
    }
    for parameter in spec.parameters:
        default = parameter.default
        if isinstance(default, str):
            decision[parameter.key] = int(default) if parameter.integer else default
        else:
            decision[parameter.key] = default.model_dump()
    if spec.share_group is not None:
        group = spec.share_group
        decision[group.key] = {
            member.key: share for member, share in zip(group.members, group.defaults, strict=True)
        }
    payload = json.dumps(decision | changes)
    model = DECISION_MODELS[spec.type.value].model_validate_json(payload)
    assert not isinstance(model, str)
    return model  # type: ignore[return-value]


@pytest.mark.parametrize("spec", CATALOG.interventions, ids=lambda spec: spec.type.value)
def test_every_decision_of_the_catalog_books_and_reconciles(spec: InterventionSpec) -> None:
    decision = default_decision(spec, **_rate_of_the_books(spec))
    plan = plan_for(decision, SAME_RATE)
    path = project(SAME_RATE, [plan])
    assert plan.decision == spec.type.value
    assert plan.entries
    assert len(path.periods) == SAME_RATE.horizon
    assert path.periods != project(SAME_RATE).periods


def _rate_of_the_books(spec: InterventionSpec) -> dict[str, object]:
    return {"current_interest_rate": "0.06"} if spec.type.value == "debt_refinance" else {}


def test_a_failed_deal_is_a_different_path() -> None:
    spec = CATALOG.spec("acquisition")
    decision = default_decision(spec)
    closed = project(SAME_RATE, [plan_for(decision, SAME_RATE)])
    failed = project(SAME_RATE, [plan_for(decision, SAME_RATE, completed=False)])
    assert closed.periods[-1].balance.goodwill > failed.periods[-1].balance.goodwill


def test_the_rate_on_the_form_must_match_the_books() -> None:
    spec = CATALOG.spec("debt_refinance")
    decision = default_decision(spec, current_interest_rate="0.12")
    with pytest.raises(FinanceError, match="current_rate_mismatch"):
        plan_for(decision, SAME_RATE)


def test_points_of_revenue_stay_points_through_the_adapter() -> None:
    spec = CATALOG.spec("rnd_change")
    decision = default_decision(
        spec,
        magnitude={"value": "2", "unit": "pp_of_revenue"},
        timing={
            "announcement_date": "2026-07-01",
            "effective_date": "2026-10-01",
            "lag_quarters": 0,
            "ramp_quarters": 0,
        },
    )
    path = project(SAME_RATE, [plan_for(decision, SAME_RATE)])
    base = project(SAME_RATE)
    second, before = path.periods[1].income, base.periods[1].income
    assert second.rd_expense - before.rd_expense == D("0.02") * before.revenue


@pytest.mark.parametrize(
    ("day", "quarter"),
    [
        (date(2026, 6, 30), 1),
        (date(2026, 7, 1), 1),
        (date(2026, 9, 30), 1),
        (date(2026, 10, 1), 2),
        (date(2026, 12, 31), 2),
        (date(2027, 6, 30), 4),
        (date(2027, 7, 1), 5),
    ],
)
def test_quarters_are_counted_from_the_base_date(day: date, quarter: int) -> None:
    assert quarter_of(date(2026, 6, 30), day) == quarter


def test_a_decision_before_the_base_date_is_refused() -> None:
    with pytest.raises(FinanceError, match="before_base_date"):
        quarter_of(date(2026, 6, 30), date(2026, 6, 1))
