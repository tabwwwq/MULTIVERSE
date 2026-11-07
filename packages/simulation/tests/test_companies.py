"""Real companies for the screens: identity, sectors and honest notes."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from multiverse_simulation.companies import (
    case_for,
    company_id_of,
    company_of,
    country_of,
    flags_of,
    medians_of,
    sector_of,
)

from multiverse_contracts.companies import Sector
from multiverse_contracts.forecasting import ForecastTarget, LiveBand, LiveCompany
from multiverse_contracts.universe import UniverseCompany


def item(**changes: Any) -> UniverseCompany:
    fields: dict[str, Any] = {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "sic": "3571",
        "division": "D",
        "xbrl_10k": 15,
        "xbrl_10q": 45,
        "first_xbrl_filed": date(2011, 1, 1),
        "last_filed": date(2026, 10, 30),
        "deregistered": False,
        "candidate": False,
        "rank": 2,
        "public_float_usd": 3.6e12,
        "float_as_of": date(2026, 3, 27),
        "tickers": ("AAPL",),
        "exchanges": ("Nasdaq",),
        "fiscal_year_end": "0926",
    } | changes
    return UniverseCompany(**fields)


@pytest.mark.parametrize(
    ("sic", "sector"),
    [
        ("3674", Sector.SEMICONDUCTORS),
        ("7372", Sector.SOFTWARE),
        ("2834", Sector.HEALTHCARE),
        ("6021", Sector.FINANCE),
        ("5331", Sector.RETAIL_WHOLESALE),
        ("2911", Sector.ENERGY_MINING),
        ("3711", Sector.TRANSPORT_EQUIPMENT),
        ("4911", Sector.UTILITIES),
        ("9999", Sector.OTHER),
        ("abcd", Sector.OTHER),
    ],
)
def test_a_sic_code_gives_a_sector(sic: str, sector: Sector) -> None:
    assert sector_of(sic) is sector


def test_a_company_keeps_one_id_across_runs() -> None:
    assert company_id_of("0000320193") == company_id_of("0000320193")
    assert company_id_of("0000320193") != company_id_of("0000789019")


def test_the_identity_comes_from_the_filer() -> None:
    company = company_of(item())
    assert company.cik == "0000320193"
    assert company.names[0].name == "Apple Inc."
    assert company.listings[0].ticker == "AAPL"
    assert company.fiscal_year_end == "09-26"
    assert company.data_origin.value == "empirical"


def test_a_filer_with_two_tickers_gets_one_open_listing() -> None:
    company = company_of(item(tickers=("BRK-B", "BRK-A"), exchanges=("NYSE", "NYSE")))
    assert [listing.ticker for listing in company.listings] == ["BRK-B"]


@pytest.mark.parametrize(
    ("code", "country"),
    [(None, "US"), ("L2", "IE"), ("X0", "GB"), ("A6", "CA"), ("Q9", "ZZ")],
)
def test_a_country_comes_from_the_business_address(code: str | None, country: str) -> None:
    assert country_of(item(country=code)) == country


def test_a_corrected_float_and_a_bank_are_flagged() -> None:
    codes = {flag.code for flag in flags_of(item(float_correction=1000.0, financial=True))}
    assert codes == {"float_scale_error", "financial_company"}
    assert flags_of(item()) == []


def live(*horizons: int) -> LiveCompany:
    bands = tuple(
        LiveBand(
            target=ForecastTarget.EBITDA_MARGIN,
            horizon=horizon,
            quarter_end=date(2027, 12, 31),
            values=(0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5),
        )
        for horizon in horizons
    )
    return LiveCompany(cik="0000320193", origin=date(2026, 12, 31), bands=bands)


def note_of(company: UniverseCompany, forecast: LiveCompany | None, folder: Path) -> str:
    found, note = case_for(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        forecast,
        company,
        (),
        date(2026, 11, 6),
        "model",
        {},
        folder,
    )
    assert found is None
    assert note is not None
    return note


def test_a_bank_has_no_case_and_says_why(tmp_path: Path) -> None:
    assert "banks" in note_of(item(financial=True), live(4, 8), tmp_path)


def test_no_forecast_means_no_case(tmp_path: Path) -> None:
    assert "No forecast" in note_of(item(), None, tmp_path)


def test_the_margins_of_the_model_are_read_by_target() -> None:
    assert medians_of(live(4, 8)) == {"ebitda_margin": {4: 0.3, 8: 0.3}}
    assert medians_of(live(4)) == {"ebitda_margin": {4: 0.3}}


def test_no_origin_to_start_from_is_a_note(tmp_path: Path) -> None:
    assert "no quarter to start from" in note_of(item(), live(4, 8), tmp_path)
