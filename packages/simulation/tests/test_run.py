"""Pairing, reproducibility, recovery and the size of a run."""

import json
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from multiverse_simulation import run as run_module
from multiverse_simulation.example import default_decision, illustrative_case
from multiverse_simulation.paths import Prepared, path_baseline
from multiverse_simulation.run import (
    ALTERNATE,
    BASELINE,
    METRICS,
    Answer,
    Draws,
    Frame,
    ReconciliationBugError,
    generator,
    simulate,
)
from multiverse_simulation.shocks import PathShocks, ShockModel, draw

from multiverse_contracts.decisions import DECISION_MODELS, DecisionModel
from multiverse_contracts.simulation import SimulationCase, SimulationSettings
from multiverse_finance.exact import FinanceError

CASE = illustrative_case(horizon=8, history_quarters=40)
SEED = 20261106


def decision(kind: str = "acquisition", **changes: object) -> DecisionModel:
    return DECISION_MODELS[kind].model_validate_json(  # type: ignore[return-value]
        json.dumps(default_decision(kind) | changes)
    )


def settings(paths: int = 40, **changes: Any) -> SimulationSettings:
    return SimulationSettings(paths=paths, seed=SEED, batch_paths=15, **changes)


def same(left: Frame, right: Frame) -> bool:
    return bool(
        np.array_equal(left.metrics, right.metrics, equal_nan=True)
        and np.array_equal(left.enterprise, right.enterprise, equal_nan=True)
        and np.array_equal(left.risks, right.risks)
        and np.array_equal(left.tail, right.tail, equal_nan=True)
    )


def test_the_same_seed_gives_the_same_numbers() -> None:
    first, _ = simulate(CASE, decision(), settings())
    second, _ = simulate(CASE, decision(), settings())
    assert same(first, second)


def test_another_seed_gives_other_numbers() -> None:
    first, _ = simulate(CASE, decision(), settings())
    other, _ = simulate(CASE, decision(), settings().model_copy(update={"seed": 1}))
    assert not same(first, other)


def test_batch_size_does_not_change_a_path() -> None:
    small, _ = simulate(CASE, decision(), settings().model_copy(update={"batch_paths": 7}))
    large, _ = simulate(CASE, decision(), settings().model_copy(update={"batch_paths": 40}))
    assert same(small, large)


def test_the_first_paths_of_a_long_run_are_the_short_run() -> None:
    short, _ = simulate(CASE, decision(), settings(20))
    long, _ = simulate(CASE, decision(), settings(40))
    assert np.array_equal(short.metrics, long.metrics[:, :20], equal_nan=True)


def test_no_decision_means_the_alternate_is_the_baseline_on_every_path() -> None:
    frame, _ = simulate(CASE, None, settings())
    assert np.array_equal(frame.metrics[BASELINE], frame.metrics[ALTERNATE])
    assert np.array_equal(frame.enterprise[BASELINE], frame.enterprise[ALTERNATE])
    assert np.array_equal(frame.risks[BASELINE], frame.risks[ALTERNATE])


def test_common_random_numbers_a_decision_never_moves_the_shared_shocks() -> None:
    plain, _ = simulate(CASE, None, settings())
    with_deal, _ = simulate(CASE, decision(), settings())
    with_capex, _ = simulate(CASE, decision("capex_expansion"), settings())
    assert np.array_equal(plain.metrics[BASELINE], with_deal.metrics[BASELINE])
    assert np.array_equal(plain.metrics[BASELINE], with_capex.metrics[BASELINE])


def test_pairing_makes_the_difference_much_less_noisy_than_unpaired_paths() -> None:
    frame, _ = simulate(CASE, decision("capex_expansion"), settings(120))
    revenue = METRICS.index("revenue")
    base = frame.metrics[BASELINE, :, -1, revenue]
    alternate = frame.metrics[ALTERNATE, :, -1, revenue]
    paired = (alternate - base).std()
    unpaired = (alternate - np.roll(base, 1)).std()
    assert paired < unpaired / 3


def test_each_uncertain_parameter_has_its_own_stream() -> None:
    draws = Draws(1, 2, 0)
    assert draws._rng("a").random() != draws._rng("b").random()
    assert draws._rng("a").random() == Draws(1, 2, 0)._rng("a").random()


def test_the_deal_closes_about_as_often_as_the_decision_says() -> None:
    frame, _ = simulate(
        CASE, decision(completion_probability="0.6"), settings(300), accounting=None
    )
    assert frame.tail[:, 3].mean() == pytest.approx(0.6, abs=0.09)


def test_a_stop_at_a_safe_point_keeps_what_is_done(tmp_path: Path) -> None:
    def stop_after_first(frame: Frame) -> Answer:
        frame.save(tmp_path / "frame.npz")
        return "stop"

    frame, answer = simulate(CASE, decision(), settings(), on_batch=stop_after_first)
    assert answer == "stop"
    assert frame.done == 15
    assert np.isnan(frame.metrics[BASELINE, 15:, 0, 0]).all()


def test_a_resumed_run_ends_in_the_same_numbers(tmp_path: Path) -> None:
    def stop_after_first(frame: Frame) -> Answer:
        frame.save(tmp_path / "frame.npz")
        return "stop"

    simulate(CASE, decision(), settings(), on_batch=stop_after_first)
    resumed, answer = simulate(
        CASE, decision(), settings(), frame=Frame.load(tmp_path / "frame.npz")
    )
    whole, _ = simulate(CASE, decision(), settings())
    assert answer == "continue"
    assert same(resumed, whole)


def test_a_checkpoint_keeps_the_refused_draws(tmp_path: Path) -> None:
    frame = Frame.empty(2, 4)
    frame.invalid = Counter({"negative_line": 3})
    frame.save(tmp_path / "frame.npz")
    assert Frame.load(tmp_path / "frame.npz").invalid == {"negative_line": 3}


def fail_first(monkeypatch: pytest.MonkeyPatch, code: str, failures: int) -> None:
    """The engine refuses the first ``failures`` attempts of path 0."""
    real = run_module.project
    calls = {"count": 0}

    def project(baseline: Any, plans: Any = ()) -> Any:
        calls["count"] += 1
        if calls["count"] <= failures:
            raise FinanceError(code, "test", "refused")
        return real(baseline, plans)

    monkeypatch.setattr(run_module, "project", project)


def test_an_impossible_draw_is_drawn_again_and_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    fail_first(monkeypatch, "negative_line", 1)
    frame, _ = simulate(CASE, None, settings(3))
    assert frame.redraws[0] == 1
    assert frame.invalid == {"negative_line": 1}
    assert np.isfinite(frame.metrics[BASELINE, 0]).all()


def test_a_path_that_stays_impossible_is_abandoned_not_invented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fail_first(monkeypatch, "negative_line", 4)
    frame, _ = simulate(CASE, None, settings(3, max_redraws=3))
    assert np.isnan(frame.metrics[BASELINE, 0]).all()
    assert np.isfinite(frame.metrics[BASELINE, 1]).all()


def test_a_path_that_does_not_reconcile_stops_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    fail_first(monkeypatch, "reconciliation", 1)
    with pytest.raises(ReconciliationBugError):
        simulate(CASE, None, settings(3))


def test_revenue_stays_positive_and_keeps_its_seasons_under_large_shocks() -> None:
    frame, _ = simulate(CASE, None, settings(60, shock_scale=4.0))
    assert (frame.metrics[BASELINE, :, :, METRICS.index("revenue")] > 0).all()


def test_shocks_reach_revenue_margin_and_rates_on_the_path() -> None:
    prepared = Prepared.of(CASE)
    model = ShockModel.of(CASE.shocks, settings())
    shocks = draw(model, generator(1, 0, 0, 0), CASE.horizon)
    baseline, clipped = path_baseline(prepared, shocks)
    quarter = baseline.quarters[0]
    margin = 1 - quarter.cogs_ratio - quarter.rd_ratio - quarter.sga_ratio
    assert float(margin) == pytest.approx(CASE.central.margin[0] + shocks.margin[0], abs=1e-5)
    assert float(quarter.rate_shift) == pytest.approx(shocks.rate_shift[0], abs=1e-6)
    assert clipped == 0


def test_revenue_grows_over_the_same_quarter_a_year_earlier_so_seasons_survive() -> None:
    seasonal = CASE.model_copy(
        update={
            "drivers": CASE.drivers.model_copy(
                update={"last_year_revenue": ("100.00", "400.00", "100.00", "400.00")}
            )
        }
    )
    quiet = PathShocks(
        np.zeros(CASE.horizon), np.zeros(CASE.horizon), np.zeros(CASE.horizon), np.zeros((1, 1))
    )
    baseline, _ = path_baseline(Prepared.of(seasonal), quiet)
    step = (2 + 0.06) / (2 - 0.06)
    revenue = [float(quarter.revenue) for quarter in baseline.quarters]
    assert revenue[0] == pytest.approx(100 * step, abs=0.01)
    assert revenue[1] == pytest.approx(400 * step, abs=0.01)
    assert revenue[4] == pytest.approx(100 * step**2, abs=0.01)


def test_a_bound_met_is_counted_never_silent() -> None:
    wild = CASE.model_copy(
        update={"central": CASE.central.model_copy(update={"margin": (0.99,) * CASE.horizon})}
    )
    prepared = Prepared.of(wild)
    model = ShockModel.of(wild.shocks, settings())
    _, clipped = path_baseline(prepared, draw(model, generator(1, 0, 0, 0), wild.horizon))
    assert clipped > 0


def run_memory(case: SimulationCase, paths: int) -> int:
    tracemalloc.start()
    simulate(case, None, SimulationSettings(paths=paths, seed=1, batch_paths=50))
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return peak


def test_memory_grows_only_with_the_arrays_of_the_frame() -> None:
    """Measured peak: a path costs its row of the frame, and statements are not kept."""
    small, large = run_memory(CASE, 100), run_memory(CASE, 300)
    per_path = (large - small) / 200
    frame_bytes = Frame.empty(1, CASE.horizon)
    row = sum(
        array.nbytes
        for array in (
            frame_bytes.metrics,
            frame_bytes.enterprise,
            frame_bytes.equity,
            frame_bytes.risks,
            frame_bytes.tail,
            frame_bytes.redraws,
            frame_bytes.clipped,
        )
    )
    assert per_path < row * 3


def test_ten_thousand_paths_fit_in_a_small_frame() -> None:
    frame = Frame.empty(10_000, 40)
    assert frame.metrics.nbytes < 30_000_000


def test_load_a_run_keeps_its_pace() -> None:
    """Far below the measured rate, so a slow machine does not fail it: it guards against a leak
    of quadratic work, not against a busy computer."""
    started = time.perf_counter()
    simulate(CASE, decision(), settings(200))
    assert time.perf_counter() - started < 60
