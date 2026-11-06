"""The run: one seed per path, both scenarios on the same shocks, batches with safe points.

Each path has its own generators, keyed by run seed, path and stream. So the result does not
depend on batch size, on a stop and resume, or on how many paths came before it: the first 500
paths of a run of 10 000 are the run of 500.

Stream 0 is exogenous and shared. Streams above it are the decision's own: a change of decision
never moves a shock. A path that the engine refuses as impossible is drawn again, and counted;
a path that does not reconcile stops the run, because that is a bug and not a bad draw.
"""

import hashlib
import json
import zlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt

from multiverse_contracts.decisions import Acquisition, DecisionModel
from multiverse_contracts.distributions import FixedValue, TriangularRange, UniformRange
from multiverse_contracts.simulation import SimulationCase, SimulationSettings
from multiverse_finance.decisions import Accounting, plan_for
from multiverse_finance.engine import project
from multiverse_finance.exact import FinanceError
from multiverse_finance.ledger import Plan
from multiverse_finance.statements import StatementPath
from multiverse_finance.valuation import enterprise_value, equity_bridge
from multiverse_simulation.paths import Prepared, path_baseline
from multiverse_simulation.shocks import Floats, PathShocks, ShockModel, draw

METRICS = ("revenue", "ebitda", "fcff", "net_debt")
RISKS = ("funding_shortfall", "covenant_breach", "below_minimum_cash", "negative_fcff_year")
TAIL_DRIVERS = ("growth_shock", "margin_shock", "rate_shift", "deal_closed")
BASELINE, ALTERNATE = 0, 1
EXOGENOUS, DECISION = 0, 1
YEAR = 4
Answer = Literal["continue", "pause", "stop"]


class ReconciliationBugError(RuntimeError):
    """A path did not reconcile: the finance engine or its caller is wrong, not the draw."""


@dataclass
class Frame:
    """Every number a report needs, per path. Grows only with paths and quarters."""

    metrics: Floats
    """[scenarios, paths, quarters, metrics]; NaN for a path abandoned after its redraws."""
    enterprise: Floats
    """[scenarios, paths]; NaN where value is undefined."""
    equity: Floats
    risks: npt.NDArray[np.bool_]
    """[scenarios, paths, risks]."""
    tail: Floats
    """[paths, tail drivers]."""
    redraws: npt.NDArray[np.int32]
    clipped: npt.NDArray[np.int32]
    done: int = 0
    invalid: Counter[str] = field(default_factory=Counter)
    """Refused draws by code, over all attempts and resumes."""

    @classmethod
    def empty(cls, paths: int, quarters: int) -> "Frame":
        return cls(
            np.full((2, paths, quarters, len(METRICS)), np.nan),
            np.full((2, paths), np.nan),
            np.full((2, paths), np.nan),
            np.zeros((2, paths, len(RISKS)), dtype=np.bool_),
            np.full((paths, len(TAIL_DRIVERS)), np.nan),
            np.zeros(paths, dtype=np.int32),
            np.zeros(paths, dtype=np.int32),
        )

    def save(self, path: Path) -> str:
        """Written whole, then moved: a stop never leaves half a checkpoint."""
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_suffix(".pending")
        with pending.open("wb") as handle:
            np.savez_compressed(  # type: ignore[arg-type,unused-ignore]
                handle,
                metrics=self.metrics,
                enterprise=self.enterprise,
                equity=self.equity,
                risks=self.risks,
                tail=self.tail,
                redraws=self.redraws,
                clipped=self.clipped,
                done=np.array(self.done),
                invalid=np.array(json.dumps(self.invalid)),
            )
        pending.replace(path)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def load(cls, path: Path) -> "Frame":
        with np.load(path) as found:
            return cls(
                found["metrics"],
                found["enterprise"],
                found["equity"],
                found["risks"],
                found["tail"],
                found["redraws"],
                found["clipped"],
                int(found["done"]),
                Counter(json.loads(str(found["invalid"]))),
            )


def generator(
    seed: int, path: int, stream: int, attempt: int, salt: int = 0
) -> np.random.Generator:
    return np.random.default_rng([seed, path, stream, attempt, salt])


@dataclass(frozen=True)
class Draws:
    """The decision's own uncertainty on one path: each parameter has its own stream."""

    seed: int
    path: int
    attempt: int

    def _rng(self, name: str) -> np.random.Generator:
        return generator(self.seed, self.path, DECISION, self.attempt, zlib.crc32(name.encode()))

    def __call__(self, name: str, shape: FixedValue | UniformRange | TriangularRange) -> Decimal:
        if isinstance(shape, FixedValue):
            return Decimal(shape.value)
        rng = self._rng(name)
        if isinstance(shape, UniformRange):
            value = rng.uniform(float(shape.low), float(shape.high))
        else:
            value = rng.triangular(float(shape.low), float(shape.mode), float(shape.high))
        return Decimal(f"{value:.6f}")

    def closes(self, decision: DecisionModel) -> bool:
        if not isinstance(decision, Acquisition):
            return True
        return bool(self._rng("completed").random() < float(decision.completion_probability))


def _record(
    frame: Frame,
    scenario: int,
    index: int,
    path: StatementPath,
    prepared: Prepared,
) -> None:
    periods = path.periods
    values = frame.metrics[scenario, index]
    for quarter, period in enumerate(periods):
        values[quarter, 0] = period.income.revenue
        values[quarter, 1] = period.income.ebitda
        values[quarter, 2] = period.free_cash.fcff
        values[quarter, 3] = period.balance.net_debt
    dcf = enterprise_value(path, prepared.capital, prepared.growth)
    bridge = equity_bridge(dcf, prepared.opening)
    if dcf.enterprise_value is not None and bridge.equity_value is not None:
        frame.enterprise[scenario, index] = float(dcf.enterprise_value)
        frame.equity[scenario, index] = float(bridge.equity_value)
    alerts = {alert for period in periods for alert in period.alerts}
    operating = np.array([float(period.free_cash.fcff_operating) for period in periods])
    yearly = np.convolve(operating, np.ones(YEAR), mode="valid")
    frame.risks[scenario, index] = (
        "funding_shortfall" in alerts,
        bool(alerts & {"leverage_breach", "interest_cover_breach"}),
        "below_minimum_cash" in alerts,
        bool((yearly < 0).any()),
    )


def _attempt(
    prepared: Prepared,
    model: ShockModel,
    decision: DecisionModel | None,
    settings: SimulationSettings,
    index: int,
    attempt: int,
    accounting: Accounting,
) -> tuple[StatementPath, StatementPath, PathShocks, int, bool]:
    exogenous = generator(settings.seed, index, EXOGENOUS, attempt)
    shocks = draw(model, exogenous, prepared.case.horizon)
    baseline, clipped = path_baseline(prepared, shocks)
    base = project(baseline)
    if decision is None:
        return base, base, shocks, clipped, True
    draws = Draws(settings.seed, index, attempt)
    closed = draws.closes(decision)
    plan: Plan = plan_for(decision, baseline, accounting, closed, draws)
    return base, project(baseline, [plan]), shocks, clipped, closed


def _one_path(
    prepared: Prepared,
    model: ShockModel,
    decision: DecisionModel | None,
    settings: SimulationSettings,
    index: int,
    frame: Frame,
    accounting: Accounting,
) -> None:
    for attempt in range(settings.max_redraws + 1):
        try:
            base, alternate, shocks, clipped, closed = _attempt(
                prepared, model, decision, settings, index, attempt, accounting
            )
        except FinanceError as error:
            if error.code == "reconciliation":
                raise ReconciliationBugError(f"path {index}: {error}") from error
            frame.invalid[error.code] += 1
            frame.redraws[index] += 1
            continue
        _record(frame, BASELINE, index, base, prepared)
        _record(frame, ALTERNATE, index, alternate, prepared)
        frame.clipped[index] = clipped
        frame.tail[index] = (
            float(shocks.growth.mean()),
            float(shocks.margin.mean()),
            float(shocks.rate_shift[-1]),
            float(closed),
        )
        return


def simulate(
    case: SimulationCase,
    decision: DecisionModel | None,
    settings: SimulationSettings,
    *,
    frame: Frame | None = None,
    on_batch: Callable[[Frame], Answer] | None = None,
    accounting: Accounting | None = None,
) -> tuple[Frame, Answer]:
    """Run or continue. ``on_batch`` is the safe point: it may save, and may ask to stop."""
    prepared = Prepared.of(case)
    model = ShockModel.of(case.shocks, settings)
    current = frame if frame is not None else Frame.empty(settings.paths, case.horizon)
    books = accounting if accounting is not None else Accounting(target_follows_baseline=True)
    answer: Answer = "continue"
    while current.done < settings.paths:
        end = min(current.done + settings.batch_paths, settings.paths)
        for index in range(current.done, end):
            _one_path(prepared, model, decision, settings, index, current, books)
        current.done = end
        if on_batch is not None:
            answer = on_batch(current)
            if answer != "continue":
                break
    return current, answer
