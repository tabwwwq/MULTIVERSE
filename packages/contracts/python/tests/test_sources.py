"""The source catalog: invariants of Stage 09 and the ways a broken catalog is refused."""

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from multiverse_contracts.source_catalog import CATALOG_PATH, SOURCE_CATALOG
from multiverse_contracts.sources import (
    AccessCategory,
    DecisionStatus,
    KeyStatus,
    Resale,
    RiskCategory,
    SourceCatalog,
)

Mutation = Callable[[dict[str, Any]], None]


def catalog_data() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SOURCE_CATALOG.model_dump_json())
    return data


def source(data: dict[str, Any], source_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(s for s in data["sources"] if s["source_id"] == source_id)
    return found


def test_generated_file_matches_the_catalog() -> None:
    written = SourceCatalog.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))
    assert written == SOURCE_CATALOG


def test_no_source_is_approved_for_download() -> None:
    assert SOURCE_CATALOG.automatic_downloads == "disabled"
    assert {s.download.status for s in SOURCE_CATALOG.sources} == {DecisionStatus.AWAITING_OWNER}


def test_access_categories_are_split_and_keys_are_explicit() -> None:
    by_access = {s.source_id: (s.access, s.key_status) for s in SOURCE_CATALOG.sources}
    assert by_access["sec-edgar"] == (AccessCategory.PUBLIC_ACCESS, KeyStatus.NOT_REQUIRED)
    assert by_access["fred-alfred"] == (AccessCategory.API_KEY, KeyStatus.OWNER_MUST_REGISTER)
    assert {need.status for need in SOURCE_CATALOG.licensed_needs} == {"not_selected"}


def test_free_access_is_not_treated_as_a_resale_licence() -> None:
    resale = {s.source_id: s.licence.resale for s in SOURCE_CATALOG.sources}
    assert resale["sec-edgar"] is Resale.NOT_GRANTED
    assert resale["fred-alfred"] is Resale.NOT_GRANTED


def test_every_source_links_its_primary_documentation_on_official_hosts() -> None:
    for item in SOURCE_CATALOG.sources:
        kinds = {link.kind for link in item.docs}
        assert kinds & {"api_reference", "documentation"}, item.source_id
        assert kinds & {"terms", "access_policy"}, item.source_id
        for dataset in item.datasets:
            assert dataset.fields, dataset.dataset_id
            assert all(endpoint.startswith("https://") for endpoint in dataset.endpoints)


def test_sec_contract_follows_fair_access() -> None:
    sec = next(s for s in SOURCE_CATALOG.sources if s.source_id == "sec-edgar")
    assert sec.rate_limit.documented_requests_per_second == "10"
    assert sec.rate_limit.chosen_requests_per_second == "2"
    rules = " ".join(sec.request_rules)
    assert "User-Agent" in rules
    assert "gzip" in rules
    assert "403" in sec.retry_policy
    assert "SHA-256" in sec.checksum_policy


def test_fred_records_vintages_and_release_dates() -> None:
    fred = next(s for s in SOURCE_CATALOG.sources if s.source_id == "fred-alfred")
    ids = {dataset.dataset_id for dataset in fred.datasets}
    assert {"fred-series-observations", "fred-series-vintagedates", "fred-release-dates"} <= ids
    observations = next(d for d in fred.datasets if d.dataset_id == "fred-series-observations")
    roles = {f.name: f.role for f in observations.fields}
    assert roles["realtime_start"] == "knowledge_time"


def test_risk_register_covers_the_required_categories() -> None:
    covered = {risk.category for risk in SOURCE_CATALOG.risks}
    required = {
        RiskCategory.REGION_AND_GAAP,
        RiskCategory.SURVIVORSHIP,
        RiskCategory.MISSING_TAGS,
        RiskCategory.QUARTERIZATION,
        RiskCategory.RESTATEMENT,
        RiskCategory.TIME_TO_PUBLICATION,
        RiskCategory.CURRENCY_AND_SCALE,
        RiskCategory.TERMS_OF_USE,
    }
    assert required <= covered


def test_ten_candidates_ranked_by_score_with_a_survivorship_case() -> None:
    candidates = SOURCE_CATALOG.candidates
    assert [c.rank for c in candidates] == list(range(1, 11))
    assert len({c.cik for c in candidates}) == 10
    acquired = [c for c in candidates if c.status == "acquired"]
    assert len(acquired) == 1
    assert acquired[0].ticker is None
    assert all(c.fiscal_year_end == "1231" for c in candidates)


def test_financial_companies_are_excluded() -> None:
    excluded = [s for s in SOURCE_CATALOG.sectors if s.priority == "excluded"]
    codes = {code for sector in excluded for code in sector.sic_codes}
    assert {"6020-6036", "6798"} <= codes


def test_catalog_contains_no_email_address() -> None:
    text = CATALOG_PATH.read_text(encoding="utf-8")
    assert re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text) is None


def _drop_terms(data: dict[str, Any]) -> None:
    sec = source(data, "sec-edgar")
    sec["docs"] = [d for d in sec["docs"] if d["kind"] not in {"terms", "access_policy"}]


def _foreign_host(data: dict[str, Any]) -> None:
    source(data, "world-bank")["docs"][0]["url"] = "https://example.com/api"


def _plain_http(data: dict[str, Any]) -> None:
    source(data, "ecb-data-portal")["docs"][0]["url"] = "http://data.ecb.europa.eu/help"


def _resale_without_licence(data: dict[str, Any]) -> None:
    source(data, "sec-edgar")["licence"]["resale"] = "allowed_by_licence"


def _key_mismatch(data: dict[str, Any]) -> None:
    source(data, "fred-alfred")["key_status"] = "not_required"


def _too_fast(data: dict[str, Any]) -> None:
    source(data, "sec-edgar")["rate_limit"]["chosen_requests_per_second"] = "20"


def _approved_without_date(data: dict[str, Any]) -> None:
    source(data, "sec-edgar")["download"]["status"] = "approved"


def _unknown_source_in_risk(data: dict[str, Any]) -> None:
    data["risks"][0]["sources"] = ["bloomberg"]


def _wrong_total(data: dict[str, Any]) -> None:
    data["candidates"][0]["total"] = 26


def _unranked(data: dict[str, Any]) -> None:
    data["candidates"][0], data["candidates"][9] = data["candidates"][9], data["candidates"][0]


def _downloads_enabled(data: dict[str, Any]) -> None:
    data["automatic_downloads"] = "enabled"


def _short_cik(data: dict[str, Any]) -> None:
    data["candidates"][0]["cik"] = "97476"


@pytest.mark.parametrize(
    "mutate",
    [
        _drop_terms,
        _foreign_host,
        _plain_http,
        _resale_without_licence,
        _key_mismatch,
        _too_fast,
        _approved_without_date,
        _unknown_source_in_risk,
        _wrong_total,
        _unranked,
        _downloads_enabled,
        _short_cik,
    ],
)
def test_a_broken_catalog_is_refused(mutate: Mutation) -> None:
    data = catalog_data()
    mutate(data)
    with pytest.raises(ValidationError):
        SourceCatalog.model_validate_json(json.dumps(data))
