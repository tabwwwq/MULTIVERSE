"""Stage 15 baselines on an invented panel: the protocol, the rows, the scores.

Each invented firm's target follows its own last value with noise, so the learned models
have something to find, and every number here comes from this file.
"""

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from multiverse_contracts.forecasting import (
    ForecastDatasetManifest,
    ForecastProtocol,
    ForecastTarget,
    Population,
    SplitName,
)
from multiverse_forecast import cli
from multiverse_forecast.benchmark import Runner, boundary, cold_start_firms, run
from multiverse_forecast.data import LAGS, load
from multiverse_forecast.models import Prep, persistence_values, seasonal_lag

TARGET = ForecastTarget.REVENUE_GROWTH
FEATURES = (
    *(c for target in ForecastTarget for c in LAGS[target]),
    "origin_quarter",
    "macro_rate",
)
HORIZONS = (1, 4)


def _quarter_end(year: int, quarter: int) -> date:
    month = 3 * quarter
    return date(year, month, 31 if month in (3, 12) else 30)


def write_dataset(folder: Path, firms: int = 40, seed: int = 7) -> Path:
    rng = np.random.default_rng(seed)
    columns = ["cik", "origin", "division", "rev_ttm", *FEATURES]
    for target in ForecastTarget:
        for h in HORIZONS:
            columns += [f"y_{target.value}_h{h}", f"r_{target.value}_h{h}"]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    origins = [_quarter_end(y, q) for y in range(2010, 2025) for q in (1, 2, 3, 4)]
    for firm in range(firms):
        cik = f"{firm + 1:010d}"
        level = rng.normal(0.05, 0.05)
        path = [level]
        for _ in range(len(origins) + 8):
            path.append(level + 0.6 * (path[-1] - level) + rng.normal(0, 0.03))
        for i, origin in enumerate(origins):
            row: dict[str, str] = {
                "cik": cik,
                "origin": origin.isoformat(),
                "division": "D" if firm % 2 else "I",
                "rev_ttm": f"{(firm + 1) * 5e6:.1f}",
                "origin_quarter": str((origin.month - 1) // 3 + 1),
                "macro_rate": f"{2 + np.sin(i / 8):.4f}",
            }
            for target in ForecastTarget:
                for k, column in enumerate(LAGS[target], start=1):
                    row[column] = f"{path[i + 4 - k]:.6f}"
                for h in HORIZONS:
                    value = path[i + 4 + h - 1]
                    released = datetime.combine(origin, datetime.min.time()) + timedelta(
                        days=91 * h + 40
                    )
                    row[f"y_{target.value}_h{h}"] = f"{value:.6f}"
                    row[f"r_{target.value}_h{h}"] = released.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            writer.writerow([row.get(c, "") for c in columns])
    text = buffer.getvalue()
    digest = hashlib.sha256(text.encode()).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "dataset.csv").write_bytes(text.encode())
    manifest = ForecastDatasetManifest.model_validate_json(
        json.dumps(
            {
                "dataset_id": f"fds-20250101-{digest[:12]}",
                "sha256": digest,
                "universe_id": "invented",
                "pit_built_at": "2025-01-02T00:00:00Z",
                "data_cutoff": "2025-01-01T05:00:00Z",
                "view": "vintage",
                "first_origin": origins[0].isoformat(),
                "last_origin": origins[-1].isoformat(),
                "horizons": list(HORIZONS),
                "targets": [t.value for t in ForecastTarget],
                "features": list(FEATURES),
                "rows": firms * len(origins),
                "companies": firms,
                "contracts_version": "0.13.0",
                "created_at": "2025-01-02T00:00:00Z",
            }
        )
    )
    (folder / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return folder


def protocol(**changes: object) -> ForecastProtocol:
    base = {
        "protocol_id": "invented",
        "seed": 3,
        "targets": ["revenue_growth"],
        "horizons": list(HORIZONS),
        "validation_years": [2017, 2018],
        "test_years": [2020, 2021, 2022],
        "cold_start_share": 0.25,
        "material_revenue": 1e8,
        "winsor_quantile": 0.01,
        "bootstrap_resamples": 200,
        "grids": {
            "persistence": [[]],
            "seasonal_naive": [[]],
            "sector_average": [[{"name": "window_quarters", "value": "8"}]],
            "panel_ar": [[]],
            "ridge": [[{"name": "alpha", "value": "1"}], [{"name": "alpha", "value": "100"}]],
            "gbm": [
                [
                    {"name": "max_depth", "value": "2"},
                    {"name": "learning_rate", "value": "0.1"},
                    {"name": "max_iter", "value": "40"},
                    {"name": "min_samples_leaf", "value": "20"},
                ]
            ],
        },
    } | changes
    return ForecastProtocol.model_validate_json(json.dumps(base))


@pytest.fixture(scope="module")
def dataset_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_dataset(tmp_path_factory.mktemp("fds") / "set")


def test_the_dataset_is_checked_against_its_hash(dataset_folder: Path, tmp_path: Path) -> None:
    data = load(dataset_folder)
    assert data.x.shape[1] == len(FEATURES)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_bytes((dataset_folder / "manifest.json").read_bytes())
    (broken / "dataset.csv").write_bytes((dataset_folder / "dataset.csv").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256"):
        load(broken)


def test_naive_forecasts_read_only_public_lags() -> None:
    assert [seasonal_lag(h) for h in (1, 2, 3, 4, 8, 12, 20)] == [3, 2, 1, 4, 4, 4, 4]
    features = ("rev_growth_l1", "rev_growth_l2", "rev_growth_l3", "rev_growth_l4")
    x = np.array([[np.nan, 0.2, 0.3, 0.4], [0.1, np.nan, np.nan, np.nan]])
    assert persistence_values(x, features, TARGET).tolist() == [0.2, 0.1]


def test_preprocessing_learns_from_training_rows_only() -> None:
    train = np.array([[1.0, 1.0], [3.0, np.nan], [5.0, 2.0]])
    features = ("a", "origin_quarter")
    prep = Prep(0.0).fit(train, features, np.array(["D", "D", "I"]))
    evaluated = prep.transform(np.array([[100.0, 3.0]]), np.array(["I"]))
    # One standardized column (mean 3, std 1.63), eleven divisions, four quarters.
    assert evaluated.shape == (1, 1 + 11 + 4)
    assert evaluated[0, 0] == pytest.approx((100 - 3) / np.std([1.0, 3.0, 5.0]))
    assert evaluated[0, 1 + 8] == 1.0  # division I
    assert evaluated[0, 1 + 11 + 2] == 1.0  # third quarter


def test_training_never_sees_a_later_target_or_a_held_out_firm(dataset_folder: Path) -> None:
    data = load(dataset_folder)
    runner = Runner(data, protocol())
    held = runner.held_out
    assert held == cold_start_firms(sorted(set(data.ciks.tolist())), 0.25, 3)
    rows = np.flatnonzero(data.years == 2021)
    fold = runner.fold(TARGET, 4, 2021, rows)
    assert fold is not None
    t = data.targets[(TARGET, 4)]
    train = ~runner.cold & ~np.isnan(t.value) & (t.released <= boundary(2021))
    assert np.all(t.released[train] <= boundary(2021))
    assert not set(data.ciks[train].tolist()) & held
    assert fold.x_train.shape[0] == int(train.sum())


def test_every_model_is_scored_on_the_same_rows(dataset_folder: Path) -> None:
    report = run(load(dataset_folder), protocol(), "0" * 64)
    again = run(load(dataset_folder), protocol(), "0" * 64)
    assert report.sha256 == again.sha256  # seeded: the same numbers every time
    groups: dict[tuple[object, ...], set[int]] = {}
    for s in report.scores:
        groups.setdefault((s.target, s.horizon, s.split, s.population), set()).add(s.examples)
    assert all(len(sizes) == 1 for sizes in groups.values())
    splits = {s.split for s in report.scores}
    assert splits == {SplitName.VALIDATION, SplitName.TEST, SplitName.COLD_START}
    assert {s.population for s in report.scores} == {Population.ALL, Population.MATERIAL}
    persistence = [s for s in report.scores if s.model == "persistence"]
    assert all(s.vs_naive == 0 for s in persistence)
    ridge = next(
        s
        for s in report.scores
        if s.model == "ridge" and s.split is SplitName.TEST and s.horizon == 4
    )
    # The series reverts to its own level: a learned model beats repeating the last value.
    assert ridge.vs_naive is not None
    assert ridge.vs_naive < 0
    assert ridge.mae_low <= ridge.mae <= ridge.mae_high
    assert len(report.findings) >= 2
    assert any("models beat persistence" in f for f in report.findings)


def test_the_command_writes_the_report(dataset_folder: Path, tmp_path: Path) -> None:
    path = tmp_path / "protocol.json"
    path.write_text(protocol().model_dump_json(), encoding="utf-8")
    code = cli.main(
        [
            "benchmark",
            "--dataset",
            str(dataset_folder),
            "--protocol",
            str(path),
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    (folder,) = [p for p in tmp_path.iterdir() if p.name.startswith("bench-")]
    assert {p.name for p in folder.iterdir()} == {"report.json", "report.md", "report.html"}
    assert "persistence" in (folder / "report.md").read_text(encoding="utf-8")
    page = (folder / "report.html").read_text(encoding="utf-8")
    assert page.count("{") == page.count("}")
    assert cli.main(["benchmark", "--dataset", str(tmp_path / "missing")]) == 2
