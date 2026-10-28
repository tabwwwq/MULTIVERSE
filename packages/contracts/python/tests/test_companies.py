"""Rules of the company contracts, checked by breaking a valid demo dossier."""

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts import CompanyDossier
from multiverse_contracts.demo import FIXTURE_PATH

Mutation = Callable[[dict[str, Any]], None]


def _northwind() -> dict[str, Any]:
    records: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(records[0])


def _overlapping_listings(d: dict[str, Any]) -> None:
    d["company"]["listings"][1]["valid_from"] = "2019-01-01"


def _two_open_names(d: dict[str, Any]) -> None:
    d["company"]["names"][0]["valid_to"] = None


def _synthetic_filing_with_link(d: dict[str, Any]) -> None:
    d["filings"][0]["url"] = "https://www.sec.gov/Archives/edgar/data/0/000.htm"


def _non_sec_link(d: dict[str, Any]) -> None:
    d["filings"][0]["url"] = "https://example.com/report.pdf"


def _value_cites_unknown_filing(d: dict[str, Any]) -> None:
    d["values"][0]["source_ids"] = ["not-a-filing"]


def _unsupported_with_values(d: dict[str, Any]) -> None:
    d["support_status"] = "unsupported"
    d["support_reason"] = "IFRS filer"


def _limited_support_without_reason(d: dict[str, Any]) -> None:
    d["support_status"] = "insufficient_history"


def _amount_in_other_currency(d: dict[str, Any]) -> None:
    d["values"][0]["quantity"]["currency"] = "EUR"


def _filing_after_cutoff(d: dict[str, Any]) -> None:
    d["filings"][0]["filed_at"] = "2024-01-01T00:00:00Z"


def _left_without_date(d: dict[str, Any]) -> None:
    d["company"]["status"] = "delisted"


def _calculated_without_formula(d: dict[str, Any]) -> None:
    value = next(v for v in d["values"] if v["metric"] == "ebitda_calculated")
    value["lineage"]["formula"] = None


def _ticker_as_lowercase(d: dict[str, Any]) -> None:
    d["company"]["listings"][1]["ticker"] = "nwsc"


BROKEN: dict[str, Mutation] = {
    "overlapping ticker periods": _overlapping_listings,
    "two current names": _two_open_names,
    "synthetic filing with a link": _synthetic_filing_with_link,
    "filing link outside sec.gov": _non_sec_link,
    "value citing an unknown filing": _value_cites_unknown_filing,
    "unsupported company with values": _unsupported_with_values,
    "limited support without a reason": _limited_support_without_reason,
    "amount in another currency": _amount_in_other_currency,
    "filing after the dossier cutoff": _filing_after_cutoff,
    "company that left without a date": _left_without_date,
    "calculated value without a formula": _calculated_without_formula,
    "lowercase ticker": _ticker_as_lowercase,
}


def test_the_baseline_dossier_is_valid() -> None:
    CompanyDossier.model_validate_json(json.dumps(_northwind()))


@pytest.mark.parametrize("mutate", BROKEN.values(), ids=BROKEN.keys())
def test_broken_dossier_is_rejected(mutate: Mutation) -> None:
    dossier = _northwind()
    mutate(dossier)

    with pytest.raises(ValidationError):
        CompanyDossier.model_validate_json(json.dumps(dossier))
