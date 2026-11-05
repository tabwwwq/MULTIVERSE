"""A stopped training goes on as if nothing happened. Skipped where PyTorch is not installed."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from multiverse_contracts.forecasting import EpochLog  # noqa: E402
from multiverse_forecast.neural import HORIZONS, TARGETS, Arrays, Config, train  # noqa: E402
from multiverse_forecast.resumable import (  # noqa: E402
    BEST,
    LAST,
    Decision,
    Identity,
    IncompatibleCheckpointError,
    clean,
    run,
)

CONFIG = Config(hidden=8, max_epochs=6, patience=6, batch_size=64, threads=1, device="cpu")
IDENTITY = Identity(
    dataset_sha256="ab" * 32,
    sequences_id="fsq-20220101-" + "cd" * 6,
    fold_year=2020,
    features=("rev_growth_l1",),
    normalization={"sequence_mean": [0.1], "sequence_std": [1.0]},
    code_commit="abc",
)
TRAIN, VALID = np.arange(0, 180), np.arange(180, 240)


def arrays() -> Arrays:
    rng = np.random.default_rng(0)
    values = rng.normal(size=(240, 6, 9))
    labels = np.full((240, len(TARGETS), len(HORIZONS)), np.nan)
    labels[:, 0, :] = np.tanh(values[:, -1, :1].repeat(len(HORIZONS), axis=1))
    labels[120:, 1, 1] = values[120:, -1, 2]
    return Arrays(values, np.ones_like(values), rng.normal(size=(240, 5)), labels)


def stop_at(epoch: int, seen: list[EpochLog]) -> "object":
    def after(entry: EpochLog, _: int, __: float, ___: str) -> Decision:
        seen.append(entry)
        return "stop" if entry.epoch == epoch else "continue"

    return after


def go_on(seen: list[EpochLog]) -> "object":
    def after(entry: EpochLog, _: int, __: float, ___: str) -> Decision:
        seen.append(entry)
        return "continue"

    return after


def test_stop_and_resume_equal_a_training_never_stopped(tmp_path: Path) -> None:
    data = arrays()
    straight = train(data, TRAIN, VALID, CONFIG)
    seen: list[EpochLog] = []
    first = run(data, TRAIN, VALID, CONFIG, IDENTITY, tmp_path, stop_at(3, seen))
    assert first.decision == "stop"
    assert first.trained is None
    assert (tmp_path / LAST).exists()
    assert (tmp_path / BEST).exists()
    second = run(data, TRAIN, VALID, CONFIG, IDENTITY, tmp_path, go_on(seen))
    assert second.trained is not None
    assert [e.epoch for e in seen] == [1, 2, 3, 4, 5, 6]
    assert [e.train_loss for e in seen] == [e.train_loss for e in straight.epochs]
    assert [e.validation_loss for e in seen] == [e.validation_loss for e in straight.epochs]
    assert [e.learning_rate for e in seen] == [e.learning_rate for e in straight.epochs]
    assert second.trained.best_epoch == straight.best_epoch
    for key, value in straight.model.state_dict().items():
        assert torch.equal(value, second.trained.model.state_dict()[key])


def test_a_stop_after_the_last_epoch_is_a_finished_training(tmp_path: Path) -> None:
    ended = run(arrays(), TRAIN, VALID, CONFIG, IDENTITY, tmp_path, stop_at(6, []))
    assert ended.decision == "continue"
    assert ended.trained is not None


@pytest.mark.parametrize(
    ("config", "identity", "named"),
    [
        (replace(CONFIG, hidden=16), IDENTITY, "hidden"),
        (replace(CONFIG, arch="tcn"), IDENTITY, "arch"),
        (replace(CONFIG, seed=5), IDENTITY, "seed"),
        (CONFIG, replace(IDENTITY, dataset_sha256="cd" * 32), "dataset_sha256"),
        (CONFIG, replace(IDENTITY, fold_year=2021), "fold_year"),
        (CONFIG, replace(IDENTITY, features=("other",)), "features"),
        (CONFIG, replace(IDENTITY, normalization={"sequence_mean": [0.2]}), "normalization"),
    ],
)
def test_resume_refuses_another_model_or_data(
    tmp_path: Path, config: Config, identity: Identity, named: str
) -> None:
    data = arrays()
    run(data, TRAIN, VALID, CONFIG, IDENTITY, tmp_path, stop_at(1, []))
    with pytest.raises(IncompatibleCheckpointError, match=named):
        run(data, TRAIN, VALID, config, identity, tmp_path, go_on([]))


def test_a_smaller_batch_may_go_on_after_running_out_of_memory(tmp_path: Path) -> None:
    data = arrays()
    run(data, TRAIN, VALID, CONFIG, IDENTITY, tmp_path, stop_at(2, []))
    seen: list[EpochLog] = []
    smaller = replace(CONFIG, batch_size=32)
    ended = run(data, TRAIN, VALID, smaller, IDENTITY, tmp_path, go_on(seen))
    assert ended.trained is not None
    assert seen[0].epoch == 3


def test_a_damaged_checkpoint_is_refused_and_a_broken_write_leaves_the_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = arrays()
    run(data, TRAIN, VALID, CONFIG, IDENTITY, tmp_path, stop_at(1, []))
    good = (tmp_path / LAST).read_bytes()

    def broken(_: object, path: Path) -> None:
        Path(path).write_bytes(b"half a file")
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(torch, "save", broken)
        with pytest.raises(OSError, match="disk full"):
            run(data, TRAIN, VALID, CONFIG, IDENTITY, tmp_path, go_on([]))
    assert (tmp_path / LAST).read_bytes() == good
    (tmp_path / LAST).write_bytes(good[:-10] + b"0123456789")
    with pytest.raises(IncompatibleCheckpointError, match="SHA-256"):
        run(data, TRAIN, VALID, CONFIG, IDENTITY, tmp_path, go_on([]))


def test_cleaning_keeps_the_best_state_only(tmp_path: Path) -> None:
    run(arrays(), TRAIN, VALID, CONFIG, IDENTITY, tmp_path, go_on([]))
    (tmp_path / "last.pending").write_bytes(b"left over")
    clean(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["best.pt", "best.sha256"]
