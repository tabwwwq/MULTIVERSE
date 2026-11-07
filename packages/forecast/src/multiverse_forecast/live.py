"""Today's forecast of every company: one fit on all that is known, then its last origin.

The benchmark answers how good the model is, on years it never saw. This answers what it says now.
Nothing can score this fit, because its targets have not happened yet: its quality is the quality
the benchmark measured, and the screen says so.

Every firm trains here, including the cold-start firms of the protocol. Early stopping still
watches a seeded tenth of the firms. Each seed is one training, and the forecast is their mean,
sorted so that quantiles never cross.
"""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

from multiverse_contracts.forecasting import (
    ForecastProtocol,
    LiveBand,
    LiveCompany,
    LiveForecast,
    Param,
)
from multiverse_forecast.benchmark import Runner
from multiverse_forecast.data import Dataset, Floats, canonical_sha256, trainable
from multiverse_forecast.neural import HORIZONS, TARGETS, Config, device_for, predict, train
from multiverse_forecast.neural_run import fold, setting
from multiverse_forecast.probabilistic import LEVELS

MODEL = "gru_attention"
SEEDS = 10
# The setting validation chose in bench-20261106-20302859cff2: the one its scores describe.
PARAMS = (
    Param(name="hidden", value="64"),
    Param(name="layers", value="1"),
    Param(name="dropout", value="0.3"),
    Param(name="max_epochs", value="80"),
    Param(name="patience", value="8"),
)


def last_rows(dataset: Dataset) -> np.ndarray:
    """The newest row of each firm."""
    order = np.argsort(dataset.origins, kind="stable")
    latest: dict[str, int] = {}
    for row in order:
        latest[str(dataset.ciks[row])] = int(row)
    return np.array(sorted(latest.values()), dtype=np.int64)


def without_unseen(dataset: Dataset, rows: np.ndarray) -> Dataset:
    """Blank a feature that only the last ``rows`` hold.

    World Bank series have no dated vintages, so point in time they exist at the newest origin
    only. No weight ever learned them, and a value there would reach the model as noise.
    """
    earlier = np.ones(dataset.x.shape[0], dtype=bool)
    earlier[rows] = False
    x = dataset.x.copy()
    x[:, ~np.isfinite(x[earlier]).any(axis=0)] = np.nan
    return replace(dataset, x=x)


def quarter_after(origin: date, quarters: int) -> date:
    """The calendar quarter end ``quarters`` after a quarter end."""
    month = origin.month + 3 * quarters
    year = origin.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = 31 if month in (3, 12) else 30
    return date(year, month, day)


def assemble(
    dataset: Dataset, rows: np.ndarray, quantiles: Floats, target_known: np.ndarray
) -> tuple[LiveCompany, ...]:
    """Bands of the targets a firm has any history of; a bank gets no EBITDA margin."""
    companies = []
    for index, row in enumerate(rows):
        origin = dataset.origins[row].astype("datetime64[D]").astype(date)
        bands = []
        for t, target in enumerate(TARGETS):
            if not target_known[row, t]:
                continue
            for h, horizon in enumerate(HORIZONS):
                values = np.sort(quantiles[index, t, h])
                if not np.isfinite(values).all():
                    continue
                bands.append(
                    LiveBand(
                        target=target,
                        horizon=horizon,
                        quarter_end=quarter_after(origin, horizon),
                        values=tuple(round(float(v), 5) for v in values),
                    )
                )
        companies.append(LiveCompany(cik=str(dataset.ciks[row]), origin=origin, bands=tuple(bands)))
    return tuple(companies)


def known_targets(dataset: Dataset) -> np.ndarray:
    """Rows by targets: whether the firm of the row has ever had that target."""
    known = np.zeros((dataset.x.shape[0], len(TARGETS)), dtype=bool)
    for t, target in enumerate(TARGETS):
        seen = np.zeros(dataset.x.shape[0], dtype=bool)
        for horizon in HORIZONS:
            found = dataset.targets.get((target, horizon))
            if found is not None:
                seen |= ~np.isnan(found.value)
        firms = set(dataset.ciks[seen].tolist())
        known[:, t] = np.isin(dataset.ciks, sorted(firms))
    return known


def fit(
    dataset: Dataset,
    sequences: Floats,
    protocol: ForecastProtocol,
    base: Config,
    out: Path,
    seeds: int = SEEDS,
    progress: Callable[[str], None] = print,
) -> LiveForecast:
    """``seeds`` trainings on everything, and the mean of their forecasts at each last origin."""
    trainable(dataset)
    rows = last_rows(dataset)
    dataset = without_unseen(dataset, rows)
    everyone = protocol.model_copy(update={"cold_start_share": 0.0})
    runner = Runner(dataset, everyone)
    year = int(dataset.years.max()) + 1
    total: Floats | None = None
    trained_rows = 0
    for number in range(seeds):
        seed = protocol.seed + number
        config = replace(setting(base, MODEL, PARAMS, seed), levels=LEVELS)
        current = fold(runner, sequences, year, seed)
        trained = train(current.data, current.train_rows, current.valid_rows, config)
        trained.model.to(device_for(config))
        forecast = predict(trained.model, current.data, rows, config)
        total = forecast if total is None else total + forecast
        trained_rows = int(current.train_rows.size)
        progress(f"seed {number + 1}/{seeds}: best epoch {trained.best_epoch}")
    if total is None:
        raise ValueError("no seeds, no forecast")
    companies = assemble(dataset, rows, total / seeds, known_targets(dataset))
    digest = canonical_sha256(
        {
            "dataset": dataset.manifest.sha256,
            "seeds": seeds,
            "seed": protocol.seed,
            "params": [param.value for param in PARAMS],
        }
    )
    built = LiveForecast(
        forecast_id=f"live-{datetime.now(UTC):%Y%m%d}-{digest[:12]}",
        dataset_id=dataset.manifest.dataset_id,
        dataset_sha256=dataset.manifest.sha256,
        model=MODEL,
        seeds=seeds,
        levels=LEVELS,
        train_rows=trained_rows,
        created_at=datetime.now(UTC),
        companies=companies,
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{built.forecast_id}.json").write_text(
        built.model_dump_json(), encoding="utf-8", newline="\n"
    )
    return built


def read(path: Path) -> LiveForecast:
    return LiveForecast.model_validate_json(
        json.dumps(json.loads(path.read_text(encoding="utf-8")))
    )
