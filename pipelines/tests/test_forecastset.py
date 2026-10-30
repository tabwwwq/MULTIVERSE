"""The Stage 15 forecasting dataset: features at the origin, released targets. Invented values."""

from datetime import UTC, date, datetime
from decimal import Decimal

from multiverse_contracts.forecasting import ForecastTarget
from multiverse_contracts.macro import AvailabilityBasis, MacroObservation
from multiverse_pipelines.forecastset.build import (
    UNDEFINED,
    _growth,
    features_at,
    macro_features,
    target_counts,
    targets_for,
    to_csv,
)
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.clock import day_end

ORIGIN = date(2021, 12, 31)


def test_growth_is_symmetric_and_bounded() -> None:
    assert _growth(Decimal(110), Decimal(100)) == 2 * 10 / 210
    assert _growth(Decimal(0), Decimal(100)) == -2.0
    assert _growth(Decimal(100), Decimal(0)) == 2.0
    # A tiny base no longer explodes: a ratio would say +999 900%.
    assert _growth(Decimal(100), Decimal("0.01")) < 2
    assert _growth(Decimal(0), Decimal(0)) is None
    assert _growth(Decimal(-5), Decimal(100)) is None


def test_features_read_lags_one_to_eight_and_never_lag_zero() -> None:
    lagged = {("revenue", k): Decimal(100 + k) for k in range(1, 9)}
    lagged |= {("operating_income", 1): Decimal(10), ("ebitda", 1): Decimal(-20)}
    lagged |= {("long_term_debt", 1): Decimal(50), ("cash", 1): Decimal(30)}
    lagged |= {("ebitda", k): Decimal(5) for k in range(2, 5)}
    lagged[("revenue", 0)] = Decimal(10**9)  # the quarter ending on the origin: not public
    row = features_at(lagged, ORIGIN)
    assert row["rev_growth_l1"] == _growth(Decimal(101), Decimal(105))
    assert row["op_margin_l1"] == 10 / 101
    assert row["ebitda_margin_l1"] == -20 / 101
    assert row["op_margin_l2"] is None
    assert row["rev_ttm"] == float(101 + 102 + 103 + 104)
    # Debt over EBITDA of the last four quarters: -20 + 5 + 5 + 5 is not positive.
    assert row["debt_to_ebitda_l1"] is None
    assert row["net_debt_to_rev_ttm"] == 20 / (101 + 102 + 103 + 104)
    assert row["history_quarters"] == 8.0
    assert row["origin_quarter"] == 4.0


def released(value: str, day: int) -> tuple[Decimal, datetime]:
    return Decimal(value), datetime(2022, 5, day, 20, tzinfo=UTC)


def test_targets_carry_their_release_and_say_undefined() -> None:
    q = date(2022, 3, 31)
    values = {
        ("revenue", q): released("120", 3),
        ("revenue", date(2021, 3, 31)): released("100", 1),
        ("operating_income", q): released("-30", 5),
        ("long_term_debt_noncurrent", q): released("40", 3),
        ("debt_current", q): released("10", 4),
        **{("ebitda", e): released("5", 2) for e in (q, date(2021, 12, 31), date(2021, 9, 30))},
        ("ebitda", date(2021, 6, 30)): released("-15", 2),
    }
    found = targets_for(values, q)
    growth, when = found[ForecastTarget.REVENUE_GROWTH]
    assert growth == 2 * 20 / 220
    assert when == datetime(2022, 5, 3, 20, tzinfo=UTC)  # the later of the two releases
    margin, when = found[ForecastTarget.OPERATING_MARGIN]
    assert margin == -30 / 120  # a loss stays in: never dropped for a nicer score
    assert when == datetime(2022, 5, 5, 20, tzinfo=UTC)
    ratio, _ = found[ForecastTarget.DEBT_TO_EBITDA]
    assert ratio == UNDEFINED  # four-quarter EBITDA 0: the multiple has no meaning
    assert ForecastTarget.FCF_MARGIN not in found  # not released at all


def test_macro_features_use_only_what_was_available_at_the_origin() -> None:
    store = MacroStore.create(None, synthetic=False, built_at=datetime(2026, 1, 1, tzinfo=UTC))
    store.register(["fred:FEDFUNDS", "fred:GDPC1"])

    def obs(series: str, start: date, value: str, public: date) -> MacroObservation:
        return MacroObservation(
            series_id=series,
            period_start=start,
            period_end=start,
            value=value,
            available_from=day_end(public),
            basis=AvailabilityBasis.VINTAGE,
            source_vintage=public,
        )

    store.add(
        [
            obs("fred:FEDFUNDS", date(2021, 11, 1), "0.08", date(2021, 12, 1)),
            obs("fred:FEDFUNDS", date(2021, 12, 1), "0.25", date(2022, 1, 3)),
            obs("fred:GDPC1", date(2020, 7, 1), "100", date(2020, 10, 29)),
            obs("fred:GDPC1", date(2021, 7, 1), "105", date(2021, 10, 28)),
        ]
    )
    row = macro_features(store, [ORIGIN])[ORIGIN]
    assert row["macro_fedfunds"] == 0.08  # December was published in January
    assert row["macro_gdp_yoy"] == float(Decimal(105) / Decimal(100) - 1)
    assert row["macro_unrate"] is None
    store.close()


def test_the_csv_is_sorted_and_stable() -> None:
    rows = [
        {"cik": "0000000002", "origin": "2021-12-31", "division": "D", "rev_ttm": 1.0},
        {
            "cik": "0000000001",
            "origin": "2021-12-31",
            "division": "I",
            "rev_ttm": None,
            "y_revenue_growth_h1": UNDEFINED,
        },
    ]
    text = to_csv(rows, {ORIGIN: {"macro_fedfunds": 0.25}})
    lines = text.splitlines()
    assert lines[1].startswith("0000000001,2021-12-31,I,,")
    assert lines[2].startswith("0000000002,2021-12-31,D,1,")
    assert to_csv(list(reversed(rows)), {ORIGIN: {"macro_fedfunds": 0.25}}) == text
    counts = {(c.target, c.horizon): c for c in target_counts(rows)}
    assert counts[(ForecastTarget.REVENUE_GROWTH, 1)].undefined == 1
