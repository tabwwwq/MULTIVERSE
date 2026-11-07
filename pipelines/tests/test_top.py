"""The ranking by public float: a filer's scale error must not decide who is largest."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from multiverse_pipelines.macro.treasury import Yields, as_of, parse
from multiverse_pipelines.sec.top import (
    Candidate,
    Listing,
    candidate_from,
    corrected,
    financial,
    load_floats,
    ranked,
    read_exchange_list,
    save_floats,
    with_exchange_list,
)

TODAY = date(2026, 11, 6)


def company(cik: str, value: float, assets: float | None = 1e11, **changes: Any) -> Candidate:
    fields: dict[str, Any] = {
        "cik": cik,
        "name": f"Company {cik}",
        "public_float": value,
        "float_as_of": date(2026, 6, 30),
        "filed": date(2026, 8, 1),
        "assets": assets,
        "earlier": None,
    } | changes
    return Candidate(**fields)


def listing(sic: str | None = "3674", tickers: tuple[str, ...] = ("ABC",)) -> Listing:
    return Listing(
        sic=sic,
        tickers=tickers,
        exchanges=("Nasdaq",),
        entity_type="operating",
        fiscal_year_end="1231",
        country=None,
        name="Company",
        xbrl_10k=10,
        xbrl_10q=30,
        first_xbrl_filed=date(2011, 1, 1),
        last_filed=date(2026, 10, 1),
    )


def _filed(end: str) -> str:
    """A 10-K comes about eight months after the middle of its fiscal year."""
    return f"{int(end[:4]) + 1}-02-15"


def facts(*rows: tuple[str, float, str]) -> dict[str, Any]:
    return {
        "entityName": "Filer",
        "facts": {
            "dei": {
                "EntityPublicFloat": {
                    "units": {
                        "USD": [
                            {"end": end, "val": value, "filed": _filed(end), "form": form}
                            for end, value, form in rows
                        ]
                    }
                }
            },
            "us-gaap": {
                "Assets": {
                    "units": {"USD": [{"end": "2026-09-30", "val": 5e9, "filed": "2026-10-20"}]}
                }
            },
        },
    }


def test_the_newest_float_of_a_10k_is_taken() -> None:
    found = candidate_from(
        "1", facts(("2024-06-30", 1e9, "10-K"), ("2025-06-30", 2e9, "10-K")), TODAY
    )
    assert found is not None
    assert found.public_float == 2e9
    assert found.earlier == 1e9
    assert found.assets == 5e9


def test_an_old_report_or_another_form_does_not_count() -> None:
    assert candidate_from("1", facts(("2023-06-30", 1e9, "10-K")), TODAY) is None
    assert candidate_from("1", facts(("2026-06-30", 1e9, "S-1")), TODAY) is None


def test_a_filer_off_the_calendar_keeps_its_float_until_the_next_10k() -> None:
    payload = facts(("2025-05-02", 9e11, "10-K"))
    rows = payload["facts"]["dei"]["EntityPublicFloat"]["units"]["USD"]
    rows[0]["filed"] = "2025-12-18"
    found = candidate_from("1", payload, TODAY)
    assert found is not None
    assert found.public_float == 9e11


def test_a_new_10k_with_an_old_date_on_the_float_still_counts() -> None:
    payload = facts(("2024-06-28", 2.6e11, "10-K"), ("2024-06-28", 2.3e11, "10-K"))
    rows = payload["facts"]["dei"]["EntityPublicFloat"]["units"]["USD"]
    rows[0]["filed"], rows[1]["filed"] = "2025-02-05", "2026-02-04"
    found = candidate_from("1", payload, TODAY)
    assert found is not None
    assert found.public_float == 2.3e11
    assert found.earlier == 2.6e11


def test_the_exchange_list_fills_in_empty_tickers(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text(
        json.dumps(
            {
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [[34088, "EXXON", "XOM", "NYSE"], [1, "NONE", "X", None]],
            }
        ),
        encoding="utf-8",
    )
    listed = read_exchange_list(path)
    assert listed == {"0000034088": [("XOM", "NYSE")]}
    empty = listing(tickers=())
    assert with_exchange_list(empty, listed, "0000034088").tickers == ("XOM",)
    assert with_exchange_list(listing(), listed, "0000034088").tickers == ("ABC",)
    assert read_exchange_list(tmp_path / "missing.json") == {}


def test_a_plausible_float_stays_as_filed() -> None:
    found = corrected(company("1", 4e12, assets=1.1e11))
    assert found is not None
    assert found.public_float == 4e12
    assert found.correction == 1


def test_thousands_tagged_as_dollars_are_scaled_back() -> None:
    found = corrected(company("1", 6.8e12, assets=1.8e9))
    assert found is not None
    assert found.public_float == 6.8e9
    assert found.correction == 1000


def test_millions_tagged_as_dollars_are_scaled_back() -> None:
    found = corrected(company("1", 4.4e15, assets=3.6e9))
    assert found is not None
    assert found.public_float == 4.4e9
    assert found.correction == 1_000_000


def test_a_bank_with_large_assets_is_held_to_its_earlier_float() -> None:
    found = corrected(company("1", 961e9, assets=18e9, earlier=2e9))
    assert found is not None
    assert found.public_float == 961e6
    assert found.correction == 1000


def test_a_float_that_grew_a_lot_but_not_absurdly_stays() -> None:
    found = corrected(company("1", 40e9, assets=2e9, earlier=2e9))
    assert found is not None
    assert found.correction == 1


def test_a_value_that_stays_impossible_is_left_out() -> None:
    assert corrected(company("1", 1e20, assets=1e6)) is None


def test_without_assets_the_earlier_float_decides() -> None:
    assert corrected(company("1", 5e9, assets=None, earlier=4e9)) is not None
    found = corrected(company("1", 5e12, assets=None, earlier=4e9))
    assert found is not None
    assert found.correction == 1000


def test_the_list_is_largest_first_and_cut_at_its_size() -> None:
    items = [company("1", 1e9), company("2", 3e9), company("3", 2e9)]
    found = ranked(items, {c.cik: listing() for c in items}, size=2)
    assert [c.cik for c in found] == ["2", "3"]


def test_funds_and_filers_without_a_code_are_left_out() -> None:
    items = [company("1", 9e9), company("2", 8e9), company("3", 7e9)]
    listings = {"1": listing(sic="6221"), "2": listing(sic=None), "3": listing()}
    assert [c.cik for c in ranked(items, listings)] == ["3"]


def test_a_large_filer_without_a_ticker_stays() -> None:
    items = [company("1", 4e11)]
    assert [c.cik for c in ranked(items, {"1": listing(tickers=())})] == ["1"]


def test_a_registrant_on_the_cover_of_its_parent_counts_once() -> None:
    items = [company("1", 5e9), company("2", 5e9)]
    listings = {"1": listing(tickers=()), "2": listing()}
    assert [c.cik for c in ranked(items, listings)] == ["2"]


def test_two_listed_companies_may_round_to_the_same_float() -> None:
    items = [company("1", 41.8e9), company("2", 41.8e9)]
    listings = {"1": listing(tickers=("AAA",)), "2": listing(tickers=("BBB",))}
    assert len(ranked(items, listings)) == 2


def test_an_absurd_earlier_float_is_no_evidence() -> None:
    found = corrected(company("1", 50.6e9, assets=41e9, earlier=37.4))
    assert found is not None
    assert found.correction == 1


def test_banks_are_marked_as_financial() -> None:
    assert financial("6021")
    assert financial("6798")
    assert not financial("3674")
    assert not financial(None)


def test_a_scan_can_be_kept_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "floats.json"
    items = [company("1", 1e9, correction=1000.0)]
    save_floats(items, path)
    assert load_floats(path) == items


def test_treasury_yields_are_read_and_found_as_of_a_day() -> None:
    rows = parse(
        'Date,"3 Mo","10 Yr"\n01/03/2022,0.08,1.63\n12/31/2021,0.06,1.52\n01/04/2022,N/A,1.66\n'
    )
    assert rows[0] == Yields(date(2021, 12, 31), 0.06, 1.52)
    assert rows[2].short is None
    assert as_of(rows, date(2022, 1, 1)) == rows[0]
    assert as_of(rows, date(2021, 12, 30)) is None
