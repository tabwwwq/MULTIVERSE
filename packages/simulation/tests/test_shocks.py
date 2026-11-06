"""The draw keeps what the history has: links between columns, and links over time."""

import numpy as np
import pytest
from multiverse_simulation.example import illustrative_case
from multiverse_simulation.run import generator
from multiverse_simulation.shocks import (
    FIRM_GROWTH,
    RATE,
    SECTOR_GROWTH,
    SECTOR_MARGIN,
    ShockModel,
    block_indices,
    draw,
)

from multiverse_contracts.simulation import SimulationSettings

CASE = illustrative_case(horizon=20, history_quarters=60)
SETTINGS = SimulationSettings(paths=1, seed=5)
MODEL = ShockModel.of(CASE.shocks, SETTINGS)


def rows_drawn(model: ShockModel, paths: int = 3000, quarters: int = 20) -> np.ndarray:
    rng = generator(1, 0, 0, 0)
    return np.stack(
        [
            model.table[block_indices(rng, len(model.table), quarters, model.mean_block)]
            for _ in range(paths)
        ]
    )


def lag_one(series: np.ndarray) -> float:
    centred = series - series.mean()
    return float((centred[:-1] * centred[1:]).sum() / (centred**2).sum())


def test_block_lengths_average_the_mean_block() -> None:
    rng = generator(2, 0, 0, 0)
    chosen = block_indices(rng, 1000, 200_000, 4.0)
    breaks = (np.diff(chosen) % 1000 != 1).sum()
    assert len(chosen) / (breaks + 1) == pytest.approx(4.0, rel=0.03)


def test_a_block_wraps_around_the_history() -> None:
    chosen = block_indices(generator(3, 0, 0, 0), 5, 50, 1000.0)
    assert set(np.diff(chosen) % 5) == {1}


def test_the_same_generator_gives_the_same_blocks() -> None:
    first = block_indices(generator(4, 7, 0, 0), 60, 20, 4.0)
    second = block_indices(generator(4, 7, 0, 0), 60, 20, 4.0)
    assert (first == second).all()


def test_every_row_drawn_is_a_whole_row_of_the_history() -> None:
    known = {tuple(row) for row in MODEL.table}
    assert all(tuple(row) in known for row in rows_drawn(MODEL, 50).reshape(-1, 6))


def test_shocks_have_no_drift() -> None:
    assert np.abs(MODEL.table.mean(axis=0)).max() < 1e-12


def test_correlation_between_columns_survives_the_draw() -> None:
    growth, margin = MODEL.column(SECTOR_GROWTH), MODEL.column(SECTOR_MARGIN)
    drawn = rows_drawn(MODEL).reshape(-1, 6)
    historical = np.corrcoef(MODEL.table[:, growth], MODEL.table[:, margin])[0, 1]
    simulated = np.corrcoef(drawn[:, growth], drawn[:, margin])[0, 1]
    assert abs(historical) > 0.3
    assert simulated == pytest.approx(historical, abs=0.03)


def test_independent_draws_would_destroy_that_correlation() -> None:
    """Why rows are drawn whole: shuffling each column alone leaves almost no link."""
    rng = np.random.default_rng(0)
    growth, margin = MODEL.column(SECTOR_GROWTH), MODEL.column(SECTOR_MARGIN)
    together = np.corrcoef(MODEL.table[:, growth], MODEL.table[:, margin])[0, 1]
    apart = np.corrcoef(
        rng.permutation(np.tile(MODEL.table[:, growth], 50)),
        rng.permutation(np.tile(MODEL.table[:, margin], 50)),
    )[0, 1]
    assert abs(apart) < abs(together) / 5


def test_blocks_keep_the_dependence_over_time() -> None:
    column = MODEL.column(SECTOR_GROWTH)
    historical = lag_one(MODEL.table[:, column])
    long_blocks = ShockModel.of(
        CASE.shocks, SimulationSettings(paths=1, seed=5, mean_block_quarters=20.0)
    )
    no_blocks = ShockModel.of(
        CASE.shocks, SimulationSettings(paths=1, seed=5, mean_block_quarters=1.0)
    )
    kept = np.mean([lag_one(path[:, column]) for path in rows_drawn(long_blocks, 800)])
    lost = np.mean([lag_one(path[:, column]) for path in rows_drawn(no_blocks, 800)])
    assert historical > 0.2
    assert kept > lost + 0.1
    assert abs(float(lost)) < 0.1


def test_deviations_decay_at_the_persistence_of_the_case() -> None:
    shocks = draw(MODEL, generator(6, 0, 0, 0), 12)
    rows = shocks.drawn
    innovation = rows[:, MODEL.column(SECTOR_GROWTH)] + rows[:, MODEL.column(FIRM_GROWTH)]
    expected = innovation[0]
    assert shocks.growth[0] == pytest.approx(expected)
    expected = MODEL.persistence_growth * expected + innovation[1]
    assert shocks.growth[1] == pytest.approx(expected)


def test_short_rates_walk_and_stop_at_zero() -> None:
    model = ShockModel.of(CASE.shocks, SimulationSettings(paths=1, seed=5, shock_scale=4.0))
    for path in range(200):
        shocks = draw(model, generator(7, path, 0, 0), 20)
        assert (shocks.rate_shift >= -model.base_short_rate).all()


def test_a_locked_macro_path_has_no_rate_moves_and_a_smaller_sector() -> None:
    locked = ShockModel.of(CASE.shocks, SimulationSettings(paths=1, seed=5, lock_macro=True))
    assert not locked.table[:, locked.column(RATE)].any()
    column = locked.column(SECTOR_GROWTH)
    assert locked.table[:, column].std() < MODEL.table[:, column].std()
    assert not draw(locked, generator(8, 0, 0, 0), 20).rate_shift.any()


def test_scale_multiplies_every_shock() -> None:
    larger = ShockModel.of(CASE.shocks, SimulationSettings(paths=1, seed=5, shock_scale=2.0))
    assert np.allclose(larger.table, MODEL.table * 2)


def test_a_history_without_a_needed_column_is_refused() -> None:
    broken = CASE.shocks.model_copy(update={"variables": ("a", "b", "c", "d", "e", "f")})
    with pytest.raises(ValueError, match="lacks"):
        ShockModel.of(broken, SETTINGS)
