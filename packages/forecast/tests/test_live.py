"""Today's forecast: which rows, which quarters, and only the targets a firm ever had."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from multiverse_contracts.forecasting import ForecastTarget, LiveBand, LiveCompany

torch = pytest.importorskip("torch")

from multiverse_forecast.data import Dataset, Targets  # noqa: E402
from multiverse_forecast.live import (  # noqa: E402
    assemble,
    known_targets,
    last_rows,
    median_of,
    quarter_after,
    without_unseen,
)
from multiverse_forecast.neural import HORIZONS, TARGETS  # noqa: E402

DAYS = np.array(["2026-06-30", "2026-09-30", "2026-03-31", "2026-06-30"], dtype="datetime64[D]")
CIKS = np.array(["0000000001", "0000000001", "0000000002", "0000000002"])


def dataset(**changes: Any) -> Any:
    fields: dict[str, Any] = {"ciks": CIKS, "origins": DAYS, "x": np.zeros((4, 1)), "targets": {}}
    return SimpleNamespace(**(fields | changes))


def test_the_newest_row_of_each_firm_is_taken() -> None:
    assert last_rows(dataset()).tolist() == [1, 3]


@pytest.mark.parametrize(
    ("origin", "quarters", "expected"),
    [
        (date(2026, 12, 31), 1, date(2027, 3, 31)),
        (date(2026, 12, 31), 4, date(2027, 12, 31)),
        (date(2026, 9, 30), 1, date(2026, 12, 31)),
        (date(2026, 6, 30), 2, date(2026, 12, 31)),
        (date(2026, 12, 31), 20, date(2031, 12, 31)),
    ],
)
def test_a_horizon_is_counted_in_calendar_quarters(
    origin: date, quarters: int, expected: date
) -> None:
    assert quarter_after(origin, quarters) == expected


def test_a_target_is_known_for_every_row_of_a_firm_that_ever_had_it() -> None:
    values = np.array([0.1, np.nan, np.nan, np.nan])
    found = Targets(
        value=values,
        undefined=np.zeros(4, dtype=bool),
        released=np.zeros(4, dtype="datetime64[D]"),
    )
    data = dataset(targets={(ForecastTarget.EBITDA_MARGIN, 1): found})
    known = known_targets(data)
    column = TARGETS.index(ForecastTarget.EBITDA_MARGIN)
    assert known[:, column].tolist() == [True, True, False, False]
    assert not known[:, TARGETS.index(ForecastTarget.REVENUE_GROWTH)].any()


def test_a_firm_gets_bands_only_for_targets_it_has() -> None:
    rows = np.array([1, 3])
    quantiles = np.tile(np.arange(7.0)[::-1], (2, len(TARGETS), len(HORIZONS), 1))
    known = np.zeros((4, len(TARGETS)), dtype=bool)
    known[1, 0] = True
    first, second = assemble(dataset(), rows, quantiles, known)
    assert {band.target for band in first.bands} == {TARGETS[0]}
    assert second.bands == ()
    assert first.origin == date(2026, 9, 30)
    assert first.bands[0].quarter_end == date(2026, 12, 31)
    assert list(first.bands[0].values) == sorted(first.bands[0].values)


def test_a_band_that_is_not_a_number_is_left_out() -> None:
    quantiles = np.full((1, len(TARGETS), len(HORIZONS), 7), np.nan)
    known = np.ones((4, len(TARGETS)), dtype=bool)
    assert assemble(dataset(), np.array([1]), quantiles, known)[0].bands == ()


def test_the_median_is_the_middle_level() -> None:
    band = LiveBand(
        target=ForecastTarget.EBITDA_MARGIN,
        horizon=4,
        quarter_end=date(2027, 12, 31),
        values=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7),
    )
    company = LiveCompany(cik="0000000001", origin=date(2026, 12, 31), bands=(band,))
    assert median_of(company, ForecastTarget.EBITDA_MARGIN, 4) == 0.4
    assert median_of(company, ForecastTarget.EBITDA_MARGIN, 8) is None


def test_a_feature_only_the_last_rows_hold_is_blanked() -> None:
    x = np.array([[1.0, np.nan, 5.0], [2.0, 7.0, np.nan], [3.0, np.nan, 6.0], [4.0, 8.0, 6.0]])
    real = Dataset(
        manifest=None,  # type: ignore[arg-type]
        ciks=CIKS,
        origins=DAYS,
        divisions=np.full(4, "D"),
        rev_ttm=np.ones(4),
        features=("a", "only_last", "b"),
        x=x,
        targets={},
    )
    blanked = without_unseen(real, np.array([1, 3]))
    assert np.isnan(blanked.x[:, 1]).all()
    assert blanked.x[1, 0] == 2.0
    assert blanked.x[3, 2] == 6.0
