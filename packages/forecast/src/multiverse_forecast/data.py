"""The forecasting dataset written by ``multiverse_pipelines.forecastset`` (Stage 15).

One row per company and forecast origin: features as known at the origin, and per target
and horizon the value as first released ("undefined" when the ratio has no meaning) with
the moment it was released. Missing values stay NaN; nothing is filled here.
"""

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt

from multiverse_contracts.forecasting import ForecastDatasetManifest, ForecastTarget

Floats = npt.NDArray[np.float64]
Bools = npt.NDArray[np.bool_]
Texts = npt.NDArray[np.str_]
UNDEFINED = "undefined"
# The latest public value of each target's own quantity, newest lag first.
LAGS: dict[ForecastTarget, tuple[str, ...]] = {
    ForecastTarget.REVENUE_GROWTH: tuple(f"rev_growth_l{k}" for k in range(1, 5)),
    ForecastTarget.OPERATING_MARGIN: tuple(f"op_margin_l{k}" for k in range(1, 5)),
    ForecastTarget.EBITDA_MARGIN: tuple(f"ebitda_margin_l{k}" for k in range(1, 5)),
    ForecastTarget.FCF_MARGIN: tuple(f"fcf_margin_l{k}" for k in range(1, 5)),
    ForecastTarget.DEBT_TO_EBITDA: ("debt_to_ebitda_l1",),
}


@dataclass(frozen=True)
class Targets:
    value: Floats
    """NaN when not released by the data cutoff or undefined."""
    undefined: Bools
    released: npt.NDArray[np.datetime64]
    """Release moment in UTC; NaT when not released."""


@dataclass(frozen=True)
class Dataset:
    manifest: ForecastDatasetManifest
    ciks: Texts
    origins: npt.NDArray[np.datetime64]
    divisions: Texts
    rev_ttm: Floats
    features: tuple[str, ...]
    x: Floats
    targets: dict[tuple[ForecastTarget, int], Targets]

    def column(self, name: str) -> Floats:
        return self.x[:, self.features.index(name)]

    @property
    def years(self) -> npt.NDArray[np.int64]:
        return self.origins.astype("datetime64[Y]").astype(np.int64) + 1970


def _float(text: str) -> float:
    return float(text) if text and text != UNDEFINED else float("nan")


def _moment(text: str) -> np.datetime64:
    if not text:
        return np.datetime64("NaT", "us")
    return np.datetime64(datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ"), "us")


def load(folder: Path) -> Dataset:
    manifest = ForecastDatasetManifest.model_validate_json((folder / "manifest.json").read_bytes())
    raw = (folder / "dataset.csv").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest.sha256:
        raise ValueError(f"{folder}: dataset.csv does not match the SHA-256 of its manifest")
    reader = csv.DictReader(raw.decode("utf-8").splitlines())
    rows = list(reader)
    features = tuple(manifest.features)
    x = np.array([[_float(r[f]) for f in features] for r in rows], dtype=np.float64)
    targets: dict[tuple[ForecastTarget, int], Targets] = {}
    for target in manifest.targets:
        for horizon in manifest.horizons:
            key = f"{target.value}_h{horizon}"
            texts = [r[f"y_{key}"] for r in rows]
            targets[(target, horizon)] = Targets(
                value=np.array([_float(t) for t in texts], dtype=np.float64),
                undefined=np.array([t == UNDEFINED for t in texts]),
                released=np.array([_moment(r[f"r_{key}"]) for r in rows]),
            )
    return Dataset(
        manifest=manifest,
        ciks=np.array([r["cik"] for r in rows]),
        origins=np.array([np.datetime64(r["origin"], "D") for r in rows]),
        divisions=np.array([r["division"] for r in rows]),
        rev_ttm=np.array([_float(r["rev_ttm"]) for r in rows], dtype=np.float64),
        features=features,
        x=x,
        targets=targets,
    )


def canonical_sha256(payload: object) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
