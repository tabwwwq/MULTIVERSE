"""Building a case from data: nothing after the origin may reach it."""

from datetime import date

import numpy as np
import pytest
from multiverse_simulation.casebuild import _deseasonalized, _innovations, shock_history

from multiverse_contracts.forecasting import ForecastDatasetManifest
from multiverse_forecast.data import Dataset

FEATURES = (
    "rev_growth_l1",
    "ebitda_margin_l1",
    "macro_fedfunds",
    "macro_gdp_yoy",
)
ORIGIN = date(2021, 12, 31)


def quarter_ends(first: int, last: int) -> np.ndarray:
    ends = ("03-31", "06-30", "09-30", "12-31")
    return np.array(
        [np.datetime64(f"{year}-{end}") for year in range(first, last) for end in ends],
        dtype="datetime64[D]",
    )


def dataset(after: float = 0.0) -> Dataset:
    """Five firms of one division over 60 quarters; ``after`` moves what follows the origin."""
    rng = np.random.default_rng(1)
    days = quarter_ends(2010, 2025)
    firms = [f"000000000{index}" for index in range(5)]
    ciks = np.repeat(firms, len(days))
    origins = np.tile(days, len(firms))
    common = rng.normal(0, 0.03, len(days))
    x = np.column_stack(
        [
            np.tile(common, len(firms)) + rng.normal(0.05, 0.03, ciks.size),
            np.tile(common / 3, len(firms)) + rng.normal(0.2, 0.01, ciks.size),
            np.tile(np.linspace(0, 5, len(days)), len(firms)),
            np.tile(common * 10, len(firms)),
        ]
    )
    late = origins > np.datetime64(ORIGIN, "D")
    x[late] += after
    return Dataset(
        manifest=ForecastDatasetManifest.model_construct(),
        ciks=ciks,
        origins=origins,
        divisions=np.full(ciks.size, "D"),
        rev_ttm=np.full(ciks.size, 1e9),
        features=FEATURES,
        x=x,
        targets={},
    )


def test_rows_end_at_the_origin() -> None:
    history = shock_history(dataset(), "0000000000", ORIGIN)
    assert history.rows[-1].quarter_end <= ORIGIN


def test_what_follows_the_origin_cannot_reach_the_case() -> None:
    """The same test the causal study has: change every later value, no shock may move."""
    first = shock_history(dataset(), "0000000000", ORIGIN)
    second = shock_history(dataset(after=1000.0), "0000000000", ORIGIN)
    assert first == second


def test_sector_and_firm_columns_add_up_to_the_shock_of_the_firm() -> None:
    history = shock_history(dataset(), "0000000000", ORIGIN)
    table = np.array([row.values for row in history.rows])
    sector, firm = table[:, 2], table[:, 3]
    assert np.corrcoef(sector, firm)[0, 1] < 0.8
    assert sector.std() > 0


def test_the_sector_column_carries_what_firms_share() -> None:
    history = shock_history(dataset(), "0000000000", ORIGIN)
    table = np.array([row.values for row in history.rows])
    assert table[:, 2].std() > table[:, 4].std()


def test_a_firm_with_too_little_history_is_refused() -> None:
    with pytest.raises(ValueError, match="quarters of shocks"):
        shock_history(dataset(), "0000000000", date(2012, 12, 31))


def test_innovations_of_a_pure_ar_process_recover_its_persistence() -> None:
    rng = np.random.default_rng(2)
    grid = np.zeros((200, 200))
    for quarter in range(1, 200):
        grid[:, quarter] = 0.6 * grid[:, quarter - 1] + rng.normal(0, 1, 200)
    _, persistence = _innovations(grid)
    assert persistence == pytest.approx(0.6, abs=0.03)


def test_a_season_is_not_a_shock() -> None:
    quarters = quarter_ends(2015, 2020)
    months = quarters.astype("datetime64[M]").astype(np.int64) % 12
    grid = np.where(months == 11, 0.3, 0.2)[None, :]
    assert np.allclose(_deseasonalized(grid, quarters), 0.0)
