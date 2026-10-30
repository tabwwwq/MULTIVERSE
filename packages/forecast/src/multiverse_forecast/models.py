"""The Stage 15 baselines, all fed the same rows (docs/06: baselines before deep learning).

- persistence: the latest public value of the target's own quantity;
- seasonal_naive: the latest public value of the same calendar quarter a year (or more)
  before the target quarter; persistence where that quarter is missing;
- sector_average: the mean target of the company's SIC division over the last two years
  of training origins (all divisions where a division has none);
- panel_ar: a pooled dynamic panel, OLS on the target's own four lags, macro controls and
  SIC division effects. Firm effects are left out: they cannot score firms never seen in
  training, and with short panels they bias the lag coefficient (Nickell);
- ridge, elastic_net: linear on every feature, standardized, with missing masks;
- gbm: gradient-boosted trees (histogram), missing values handled natively.

Every learned transform (winsor bounds, medians, scales) is fitted on the training rows
of the fold only; the training target is winsorized at its own training quantiles, the
evaluated target never is.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNet, Ridge

from multiverse_contracts.forecasting import ForecastTarget, Param
from multiverse_forecast.data import LAGS, Floats, Texts

DIVISIONS = tuple("ABCDEFGHIJK")


@dataclass(frozen=True)
class Fold:
    target: ForecastTarget
    horizon: int
    features: tuple[str, ...]
    x_train: Floats
    y_train: Floats
    divisions_train: Texts
    quarters_train: np.ndarray
    """Origin of each training row as a quarter index (year * 4 + quarter)."""
    x_eval: Floats
    divisions_eval: Texts
    quantile: float
    seed: int


class Model(Protocol):
    name: str

    def fit(self, fold: Fold) -> None: ...

    def predict(self, fold: Fold) -> Floats: ...


def latest(x: Floats, features: Sequence[str], columns: Sequence[str]) -> Floats:
    """The first non-missing value among columns, newest first."""
    found = np.full(x.shape[0], np.nan)
    for column in reversed(columns):
        values = x[:, features.index(column)]
        found = np.where(np.isnan(values), found, values)
    return found


def persistence_values(x: Floats, features: Sequence[str], target: ForecastTarget) -> Floats:
    return latest(x, features, LAGS[target])


def seasonal_lag(horizon: int) -> int:
    """Lag of the latest public quarter in the target quarter's calendar position."""
    return 4 * (horizon // 4 + 1) - horizon


def seasonal_values(
    x: Floats, features: Sequence[str], target: ForecastTarget, horizon: int
) -> Floats:
    columns = LAGS[target]
    lag = seasonal_lag(horizon)
    base = persistence_values(x, features, target)
    if lag > len(columns):
        return base
    values = x[:, features.index(columns[lag - 1])]
    return np.where(np.isnan(values), base, values)


def _clip_bounds(values: Floats, quantile: float) -> tuple[Floats, Floats]:
    if quantile == 0:
        return np.full(values.shape[1:], -np.inf), np.full(values.shape[1:], np.inf)
    with np.errstate(all="ignore"):
        low = np.nanquantile(values, quantile, axis=0)
        high = np.nanquantile(values, 1 - quantile, axis=0)
    return np.where(np.isnan(low), -np.inf, low), np.where(np.isnan(high), np.inf, high)


def winsorized_target(fold: Fold) -> Floats:
    low, high = _clip_bounds(fold.y_train[:, None], fold.quantile)
    return np.clip(fold.y_train, low[0], high[0])


@dataclass
class Prep:
    """Train-only winsorizing, imputation with masks, scaling and one-hot columns."""

    quantile: float
    impute: bool = True
    scale: bool = True
    columns: tuple[int, ...] = ()
    low: Floats = field(default_factory=lambda: np.zeros(0))
    high: Floats = field(default_factory=lambda: np.zeros(0))
    median: Floats = field(default_factory=lambda: np.zeros(0))
    masked: tuple[int, ...] = ()
    mean: Floats = field(default_factory=lambda: np.zeros(0))
    std: Floats = field(default_factory=lambda: np.zeros(0))
    quarter: int | None = None

    def fit(self, x: Floats, features: Sequence[str], divisions: Texts) -> "Prep":
        self.quarter = features.index("origin_quarter") if "origin_quarter" in features else None
        self.columns = tuple(
            i for i in range(x.shape[1]) if i != self.quarter and not np.all(np.isnan(x[:, i]))
        )
        part = x[:, self.columns]
        self.low, self.high = _clip_bounds(part, self.quantile)
        clipped = np.clip(part, self.low, self.high)
        self.median = np.nan_to_num(np.nanmedian(clipped, axis=0))
        self.masked = tuple(j for j in range(part.shape[1]) if np.isnan(part[:, j]).any())
        filled = self._core(part)
        self.mean = filled.mean(axis=0)
        self.std = np.where(filled.std(axis=0) > 0, filled.std(axis=0), 1.0)
        return self

    def _core(self, part: Floats) -> Floats:
        clipped = np.clip(part, self.low, self.high)
        if not self.impute:
            return clipped
        filled = np.where(np.isnan(clipped), self.median, clipped)
        masks = np.isnan(part[:, list(self.masked)]).astype(np.float64)
        return np.hstack([filled, masks])

    def transform(self, x: Floats, divisions: Texts) -> Floats:
        core = self._core(x[:, self.columns])
        if self.scale:
            core = (core - self.mean) / self.std
        blocks = [core, np.stack([divisions == d for d in DIVISIONS], axis=1).astype(np.float64)]
        if self.quarter is not None:
            q = x[:, self.quarter]
            blocks.append(np.stack([q == k for k in (1, 2, 3, 4)], axis=1).astype(np.float64))
        return np.hstack(blocks)


@dataclass
class Persistence:
    name: str = "persistence"

    def fit(self, fold: Fold) -> None:
        return None

    def predict(self, fold: Fold) -> Floats:
        return persistence_values(fold.x_eval, fold.features, fold.target)


@dataclass
class SeasonalNaive:
    name: str = "seasonal_naive"

    def fit(self, fold: Fold) -> None:
        return None

    def predict(self, fold: Fold) -> Floats:
        return seasonal_values(fold.x_eval, fold.features, fold.target, fold.horizon)


@dataclass
class SectorAverage:
    window_quarters: int = 8
    name: str = "sector_average"
    means: dict[str, float] = field(default_factory=dict)
    overall: float = 0.0

    def fit(self, fold: Fold) -> None:
        y = winsorized_target(fold)
        recent = fold.quarters_train > fold.quarters_train.max() - self.window_quarters
        self.overall = float(np.mean(y[recent]))
        self.means = {
            d: float(np.mean(y[recent & (fold.divisions_train == d)]))
            for d in DIVISIONS
            if np.any(recent & (fold.divisions_train == d))
        }

    def predict(self, fold: Fold) -> Floats:
        return np.array([self.means.get(str(d), self.overall) for d in fold.divisions_eval])


@dataclass
class PanelAR:
    name: str = "panel_ar"
    prep: Prep | None = None
    used: tuple[str, ...] = ()
    coef: Floats = field(default_factory=lambda: np.zeros(0))

    def _x(self, fold: Fold, x: Floats) -> Floats:
        return x[:, [fold.features.index(c) for c in self.used]]

    def fit(self, fold: Fold) -> None:
        macro = tuple(f for f in fold.features if f.startswith("macro_"))
        self.used = (*LAGS[fold.target], *macro)
        part = self._x(fold, fold.x_train)
        self.prep = Prep(fold.quantile, impute=True, scale=False).fit(
            part, self.used, fold.divisions_train
        )
        design = self.prep.transform(part, fold.divisions_train)
        self.coef = np.linalg.lstsq(design, winsorized_target(fold), rcond=None)[0]

    def predict(self, fold: Fold) -> Floats:
        assert self.prep is not None
        design = self.prep.transform(self._x(fold, fold.x_eval), fold.divisions_eval)
        return np.asarray(design @ self.coef, dtype=np.float64)


@dataclass
class Learned:
    """A scikit-learn regressor behind the shared train-only preprocessing."""

    name: str
    params: dict[str, float]
    prep: Prep | None = None
    model: object = None

    def _estimator(self, seed: int) -> object:
        if self.name == "ridge":
            return Ridge(alpha=self.params["alpha"])
        if self.name == "elastic_net":
            return ElasticNet(
                alpha=self.params["alpha"],
                l1_ratio=self.params["l1_ratio"],
                max_iter=5000,
                random_state=seed,
            )
        return HistGradientBoostingRegressor(
            max_depth=int(self.params["max_depth"]),
            learning_rate=self.params["learning_rate"],
            max_iter=int(self.params["max_iter"]),
            min_samples_leaf=int(self.params["min_samples_leaf"]),
            early_stopping=False,
            random_state=seed,
        )

    def fit(self, fold: Fold) -> None:
        trees = self.name == "gbm"
        self.prep = Prep(fold.quantile, impute=not trees, scale=not trees).fit(
            fold.x_train, fold.features, fold.divisions_train
        )
        self.model = self._estimator(fold.seed)
        design = self.prep.transform(fold.x_train, fold.divisions_train)
        self.model.fit(design, winsorized_target(fold))  # type: ignore[attr-defined]

    def predict(self, fold: Fold) -> Floats:
        assert self.prep is not None
        design = self.prep.transform(fold.x_eval, fold.divisions_eval)
        return np.asarray(self.model.predict(design), dtype=np.float64)  # type: ignore[attr-defined]


def make(name: str, params: Sequence[Param]) -> Model:
    values = {p.name: float(p.value) for p in params}
    if name == "persistence":
        return Persistence()
    if name == "seasonal_naive":
        return SeasonalNaive()
    if name == "sector_average":
        return SectorAverage(window_quarters=int(values.get("window_quarters", 8)))
    if name == "panel_ar":
        return PanelAR()
    if name in ("ridge", "elastic_net", "gbm"):
        return Learned(name, values)
    raise ValueError(f"unknown model {name!r}")


def applies(name: str, target: ForecastTarget) -> bool:
    """Debt over EBITDA is a stock ratio: no seasonal pattern to repeat."""
    return not (name == "seasonal_naive" and target is ForecastTarget.DEBT_TO_EBITDA)
