"""Trainings that can stop and go on (Stage 18): the same result as if nothing happened.

After every epoch the state goes to ``last.pt``, and to ``best.pt`` when the validation
loss improved. A file holds model, optimizer, scheduler, every random state, the loop's
counters, the normalization of the fold and what the data looked like. It is written next
to its target, flushed, renamed over it and followed by its SHA-256, so a crash leaves the
previous file whole. Files hold plain tensors and text: ``weights_only=True`` loads them.

Resume refuses a file of another model, data, fold or feature schema: it would continue
something else under the same name.
"""

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import torch

from multiverse_contracts.forecasting import EpochLog
from multiverse_forecast.data import canonical_sha256
from multiverse_forecast.neural import (
    Arrays,
    Config,
    Progress,
    Trained,
    begin,
    device_for,
    finished,
    step,
)

FORMAT = 1
LAST = "last.pt"
BEST = "best.pt"
Decision = Literal["continue", "pause", "stop"]
AfterEpoch = Callable[[EpochLog, int, float, str], Decision]


class IncompatibleCheckpointError(ValueError):
    """The checkpoint belongs to another model, dataset or schema."""


@dataclass(frozen=True)
class Identity:
    """What a resumed training must have in common with the one that stopped."""

    dataset_sha256: str
    sequences_id: str
    fold_year: int
    features: tuple[str, ...]
    normalization: dict[str, list[float]]
    code_commit: str

    def required(self, config: Config) -> dict[str, object]:
        """Everything that must match; the batch size may shrink after running out of memory,
        and a checkout of another commit may go on with the same model."""
        return {
            "format": FORMAT,
            "dataset_sha256": self.dataset_sha256,
            "sequences_id": self.sequences_id,
            "fold_year": self.fold_year,
            "features": canonical_sha256(list(self.features)),
            "normalization": canonical_sha256(self.normalization),
            "arch": config.arch,
            "hidden": config.hidden,
            "layers": config.layers,
            "dropout": config.dropout,
            "levels": list(config.levels),
            "seed": config.seed,
        }


@dataclass(frozen=True)
class Stopped:
    """How a run ended: finished, or stopped at a safe point."""

    decision: Decision
    trained: Trained | None
    checkpoint_sha256: str


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(path: Path, blob: dict[str, object]) -> str:
    """The file appears whole or not at all, with its SHA-256 beside it."""
    pending = path.with_suffix(".pending")
    torch.save(blob, pending)
    with pending.open("r+b") as handle:
        os.fsync(handle.fileno())
    digest = _digest(pending)
    pending.replace(path)
    path.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
    return digest


def snapshot(
    progress: Progress, config: Config, identity: Identity, batch_size: int
) -> dict[str, object]:
    cuda = device_for(config).type == "cuda"
    return {
        "model": progress.model.state_dict(),
        "optimizer": progress.optimizer.state_dict(),
        "scheduler": progress.scheduler.state_dict(),
        "rng_numpy": json.dumps(progress.rng.bit_generator.state),
        "rng_torch": torch.get_rng_state(),
        "rng_cuda": torch.cuda.get_rng_state_all() if cuda else [],
        "epochs": json.dumps([e.model_dump() for e in progress.epochs]),
        "best": progress.best,
        "best_epoch": progress.best_epoch,
        "best_state": progress.best_state,
        "stale": progress.stale,
        "batch_size": batch_size,
        "required": json.dumps(identity.required(config), sort_keys=True),
        "normalization": json.dumps(identity.normalization),
        "code_commit": identity.code_commit,
    }


def restore(path: Path, progress: Progress, config: Config, identity: Identity) -> None:
    """Back to the moment of the file, or a refusal; nothing changes on a refusal."""
    expected = path.with_suffix(".sha256")
    if expected.exists() and expected.read_text(encoding="utf-8").strip() != _digest(path):
        raise IncompatibleCheckpointError(f"{path.name} does not match its SHA-256")
    blob = torch.load(path, map_location="cpu", weights_only=True)
    found = json.loads(blob["required"])
    wanted = json.loads(json.dumps(identity.required(config), sort_keys=True))
    differ = sorted(k for k in wanted if found.get(k) != wanted[k])
    if differ:
        raise IncompatibleCheckpointError(f"{path.name} differs in {', '.join(differ)}")
    device = device_for(config)
    progress.model.load_state_dict(blob["model"])
    progress.optimizer.load_state_dict(blob["optimizer"])
    progress.scheduler.load_state_dict(blob["scheduler"])
    progress.rng.bit_generator.state = json.loads(blob["rng_numpy"])
    torch.set_rng_state(blob["rng_torch"])
    if device.type == "cuda" and blob["rng_cuda"]:
        torch.cuda.set_rng_state_all(blob["rng_cuda"])
    progress.epochs = [EpochLog.model_validate(e) for e in json.loads(blob["epochs"])]
    progress.best = float(blob["best"])
    progress.best_epoch = int(blob["best_epoch"])
    state = blob["best_state"]
    progress.best_state = None if state is None else {k: v.to(device) for k, v in state.items()}
    progress.stale = int(blob["stale"])


def run(
    data: Arrays,
    train_rows: np.ndarray,
    valid_rows: np.ndarray,
    config: Config,
    identity: Identity,
    folder: Path,
    after_epoch: AfterEpoch,
) -> Stopped:
    """Trains from the last checkpoint of the folder, or from the start; after each epoch
    the state is safe on disk and ``after_epoch`` may ask to stop there."""
    folder.mkdir(parents=True, exist_ok=True)
    last, best = folder / LAST, folder / BEST
    progress, placed = begin(data, config)
    if last.exists():
        restore(last, progress, config, identity)
    digest = ""
    while True:
        more = step(progress, placed, train_rows, valid_rows, config)
        blob = snapshot(progress, config, identity, config.batch_size)
        digest = publish(last, blob)
        if progress.best_epoch == len(progress.epochs):
            shutil.copyfile(last, best)
            best.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
        decision = after_epoch(progress.epochs[-1], progress.best_epoch, progress.best, digest)
        if not more:
            return Stopped("continue", finished(progress), digest)
        if decision != "continue":
            return Stopped(decision, None, digest)


def clean(folder: Path) -> None:
    """After a finished training only the best state stays; half-written files never do."""
    for pending in folder.glob("*.pending"):
        pending.unlink()
    for name in (LAST, Path(LAST).with_suffix(".sha256").name):
        (folder / name).unlink(missing_ok=True)
