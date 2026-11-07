"""Untrusted files never run, and blocked datasets never train (Stage 24)."""

import json
import pickle
from pathlib import Path
from typing import Any

import pytest

from multiverse_contracts.forecasting import ForecastDatasetManifest
from multiverse_contracts.source_catalog import FRED, blocked_for_training
from multiverse_forecast import data as forecast_data
from multiverse_forecast.data import LicenceBlockedError, trainable

SHA = "ab" * 32
MANIFEST: dict[str, Any] = {
    "dataset_id": f"fds-20261028-{SHA[:12]}",
    "sha256": SHA,
    "universe_id": "invented",
    "pit_built_at": "2026-10-28T00:00:00Z",
    "data_cutoff": "2026-10-28T05:00:00Z",
    "view": "vintage",
    "first_origin": "2010-03-31",
    "last_origin": "2026-09-30",
    "horizons": [1],
    "targets": ["revenue_growth"],
    "features": ["rev_growth_l1"],
    "rows": 1,
    "companies": 1,
    "contracts_version": "0.22.0",
    "created_at": "2026-10-28T00:00:00Z",
}
RAN: list[str] = []


class Payload:
    """What a hostile checkpoint holds: an object that runs code when it is unpickled."""

    def __reduce__(self) -> tuple[Any, tuple[str]]:
        return (RAN.append, ("the payload ran",))


class Holder:
    def __init__(self, series: tuple[str, ...]) -> None:
        self.manifest = ForecastDatasetManifest.model_validate_json(
            json.dumps(MANIFEST | {"macro_series": list(series)})
        )


def holder(*series: str) -> Any:
    return Holder(series)


def test_a_dataset_on_fred_series_does_not_train() -> None:
    with pytest.raises(LicenceBlockedError, match="fred:FEDFUNDS"):
        trainable(holder("fred:FEDFUNDS", "ecb:EXR"))


def test_a_dataset_without_them_trains() -> None:
    trainable(holder("ecb:EXR", "worldbank:NY.GDP"))
    trainable(holder())


def test_only_the_blocked_series_are_named() -> None:
    assert blocked_for_training(["fred:DGS10", "ecb:EXR"]) == ("fred:DGS10",)


def test_a_resolved_block_lifts_the_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved = tuple(
        block.model_copy(update={"status": "resolved"})
        if block.use == "machine_learning"
        else block
        for block in FRED.blocks
    )
    lifted = FRED.model_copy(update={"blocks": resolved})
    monkeypatch.setattr("multiverse_contracts.source_catalog.FRED", lifted)
    assert blocked_for_training(["fred:DGS10"]) == ()


def test_every_way_into_a_fit_asks_first() -> None:
    root = Path(forecast_data.__file__).parent
    for name, count in (("benchmark", 1), ("neural_run", 2), ("evaluation", 1), ("cli", 1)):
        assert (root / f"{name}.py").read_text(encoding="utf-8").count(
            "trainable(dataset)"
        ) == count


def hostile(path: Path) -> Path:
    path.write_bytes(pickle.dumps({"state_dict": Payload()}))
    return path


def test_a_hostile_checkpoint_never_runs(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    from multiverse_forecast.neural import load_checkpoint

    RAN.clear()
    with pytest.raises(Exception, match=r"(?i)weights|pickle|unsupported|zip|load"):
        load_checkpoint(hostile(tmp_path / "best.pt"))
    assert RAN == []


def test_a_checkpoint_with_a_forged_hash_is_refused_before_it_is_read(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    from multiverse_forecast import resumable

    path = hostile(tmp_path / "last.pt")
    path.with_suffix(".sha256").write_text("00" * 32, encoding="utf-8")
    RAN.clear()
    with pytest.raises(resumable.IncompatibleCheckpointError, match="SHA-256"):
        resumable.restore(path, None, None, None)  # type: ignore[arg-type]
    assert RAN == []
