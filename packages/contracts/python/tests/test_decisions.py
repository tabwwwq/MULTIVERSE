"""Decision contracts and the intervention catalog (Stage 05)."""

import json
import random
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts import CATALOG, InterventionSpec, ScenarioDraft
from multiverse_contracts.catalog import CATALOG_PATH, render
from multiverse_contracts.decisions import DECISION_MODELS, add_quarters

NORTHWIND = "5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13"
SHARED_FIELDS = {"type", "magnitude", "timing"}


def _default_decision(spec: InterventionSpec) -> dict[str, Any]:
    unit = spec.magnitude.default_unit or spec.magnitude.units[0].unit
    unit_spec = next(u for u in spec.magnitude.units if u.unit == unit)
    decision: dict[str, Any] = {
        "type": spec.type.value,
        "magnitude": {"value": unit_spec.default_value, "unit": unit.value},
        "timing": {
            "announcement_date": "2022-12-31",
            "effective_date": "2023-01-01",
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
    return decision


def _draft(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "contracts_version": "0.3.0",
        "company_id": NORTHWIND,
        "as_of": "2022-12-31",
        "data_origin": "synthetic",
        "horizon_quarters": 20,
        "seed": CATALOG.default_seed,
        "decision": decision,
        "sensitivity": {"parameters": [], "points": CATALOG.default_sensitivity_points},
    }


def _validate(payload: dict[str, Any]) -> ScenarioDraft:
    return ScenarioDraft.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("spec", CATALOG.interventions, ids=lambda spec: spec.type.value)
def test_catalog_defines_exactly_the_fields_of_the_model(spec: InterventionSpec) -> None:
    model = DECISION_MODELS[spec.type.value]
    expected = SHARED_FIELDS | {parameter.key for parameter in spec.parameters}
    if spec.share_group is not None:
        expected.add(spec.share_group.key)

    assert set(model.model_fields) == expected


@pytest.mark.parametrize("spec", CATALOG.interventions, ids=lambda spec: spec.type.value)
def test_documented_defaults_form_a_valid_scenario(spec: InterventionSpec) -> None:
    draft = _validate(_draft(_default_decision(spec)))

    assert draft.decision.type == spec.type.value


def test_every_default_names_its_source() -> None:
    for spec in CATALOG.interventions:
        for parameter in spec.parameters:
            assert parameter.default_source.note.strip()
        assert spec.magnitude.default_source.note.strip()


def test_rnd_unit_has_no_default_because_it_changes_the_meaning() -> None:
    rnd = CATALOG.spec("rnd_change")

    assert rnd.magnitude.default_unit is None
    assert {unit.unit.value for unit in rnd.magnitude.units} == {
        "fraction_of_previous_rnd_budget",
        "pp_of_revenue",
    }


def test_financing_shares_must_add_up_to_exactly_one() -> None:
    rng = random.Random(20261028)
    base = _draft(_default_decision(CATALOG.spec("acquisition")))
    for _ in range(300):
        cash, debt = sorted(rng.randint(0, 100) for _ in range(2))
        shares = [cash, debt - cash, 100 - debt]
        if rng.random() < 0.5:
            shares[rng.randrange(3)] += rng.choice([-1, 1]) * rng.randint(1, 5)
        if min(shares) < 0:
            continue
        mix = [str(Decimal(share) / 100) for share in shares]
        base["decision"]["financing"] = dict(zip(("cash", "debt", "equity"), mix, strict=True))

        if sum(shares) == 100:
            _validate(base)
        else:
            with pytest.raises(ValidationError, match=r"\[shares_sum\]"):
                _validate(base)


def test_shares_are_compared_as_decimals_not_floats() -> None:
    # 0.7 + 0.2 + 0.1 is 0.9999999999999999 in binary floating point, but exactly 1 here.
    payload = _draft(_default_decision(CATALOG.spec("capex_expansion")))
    payload["decision"]["financing"] = {"cash": "0.7", "debt": "0.2", "equity": "0.1"}

    _validate(payload)


def test_out_of_distribution_values_are_allowed_inside_the_hard_limits() -> None:
    payload = _draft(_default_decision(CATALOG.spec("rnd_change")))
    payload["decision"]["magnitude"] = {"value": "5", "unit": "fraction_of_previous_rnd_budget"}

    _validate(payload)


@pytest.mark.parametrize(
    ("start", "quarters", "expected"),
    [
        (date(2022, 12, 31), 1, date(2023, 3, 31)),
        (date(2022, 11, 30), 1, date(2023, 2, 28)),
        (date(2023, 11, 30), 1, date(2024, 2, 29)),
        (date(2022, 12, 31), 20, date(2027, 12, 31)),
    ],
)
def test_add_quarters_clamps_to_the_end_of_a_short_month(
    start: date, quarters: int, expected: date
) -> None:
    assert add_quarters(start, quarters) == expected


def test_catalog_file_is_up_to_date() -> None:
    assert CATALOG_PATH.read_text(encoding="utf-8") == render()
