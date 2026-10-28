"""The synthetic demo fixtures are up to date, valid and honest about being fictional."""

import json
from typing import Any

import pytest

from multiverse_contracts import CompanyDossier
from multiverse_contracts.demo import FIXTURE_PATH, render


def _records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return records


def _by_ticker(ticker: str) -> dict[str, Any]:
    for record in _records():
        if record["company"]["listings"][-1]["ticker"] == ticker:
            return record
    raise AssertionError(f"no demo company with ticker {ticker}")


def test_committed_fixture_matches_the_generator() -> None:
    assert FIXTURE_PATH.read_text(encoding="utf-8") == render(), (
        "fixtures/demo/companies.json is stale. Run: npm run contracts:gen"
    )


@pytest.mark.parametrize("record", _records(), ids=lambda r: r["company"]["names"][-1]["name"])
def test_every_record_is_a_valid_dossier(record: dict[str, Any]) -> None:
    CompanyDossier.model_validate_json(json.dumps(record))


def test_demo_universe_is_fictional_and_synthetic() -> None:
    records = _records()
    assert len(records) == 7
    assert len({r["company"]["company_id"] for r in records}) == 7
    for record in records:
        assert record["company"]["data_origin"] == "synthetic"
        assert record["company"]["cik"].startswith("0099"), "fictional CIKs stay outside SEC ranges"
        assert all(filing["url"] is None for filing in record["filings"]), "no invented links"


def test_missing_values_are_never_zero() -> None:
    for record in _records():
        for value in record["values"]:
            if value["quantity"] is None:
                assert value["missing_reason"]
            else:
                assert value["missing_reason"] is None


def test_scenarios_needed_by_the_explorer_exist() -> None:
    northwind = _by_ticker("NWSC")
    assert [listing["ticker"] for listing in northwind["company"]["listings"]] == ["NWMD", "NWSC"]
    assert len(northwind["company"]["names"]) == 2

    assert _by_ticker("AGRU")["company"]["status"] == "acquired"
    assert _by_ticker("TSLG")["support_status"] == "insufficient_history"

    valtrix = _by_ticker("VLTX")
    assert valtrix["support_status"] == "unsupported"
    assert valtrix["company"]["accounting_standard"] == "ifrs"
    assert valtrix["values"] == []

    kestrel = _by_ticker("KSTL")
    fy2020 = [v for v in kestrel["values"] if v["period"]["end_date"].startswith("2020")]
    assert fy2020
    assert all(v["quantity"] is None and "CAD" in v["missing_reason"] for v in fy2020)
