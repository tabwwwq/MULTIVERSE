"""A temporal neural network on point-in-time history (Stage 16): GRU with attention.

Inputs, per row (a company and a forecast origin), all as known at the origin:

- ``sequence``: [24 quarters, 9 channels], oldest quarter first (lag 24 .. lag 1), with a
  mask [24, 9] of observed values. Channels: symmetric revenue growth, log revenue,
  operating, EBITDA and FCF margins, capex and R&D intensity, cash over trailing revenue,
  debt over trailing EBITDA. Ratios enter as asinh(x / 0.1), so a margin of -300 does not
  drown a margin of 0.1; then every channel is standardized on the training rows.
- ``static``: the Stage 15 tabular features (macro at the origin, size, SIC division,
  quarter), with the same train-only preprocessing as the linear baselines.

Encoders (``Config.arch``): ``gru_attention``, a GRU over the quarters; ``tcn``, a stack of
causal dilated convolutions (dilations 1, 2, 4, 8: every state sees up to 31 quarters back,
never forward). Both feed the same additive attention, last state and head.

Output: [5 targets, 5 horizons, levels], by default the quantiles 0.1, 0.5 and 0.9; Stage
17 trains seven levels. Quantiles cannot cross: the median is free, and each outer quantile
lies one softplus beyond its neighbour. Targets are learned in a space that respects them:

- revenue growth (between -2 and 2): 2 * tanh(z), bounded and smooth, never clipped;
- margins: asinh(y / 0.1), unbounded, tails compressed; back-transformed by 0.1 * sinh;
- debt / EBITDA (not negative where defined): asinh(y) through softplus(z), so a forecast
  is never negative and the gradient never dies at zero, unlike a clamp.

Loss: pinball loss in that space, each (target, horizon) weighted equally, averaged over
the labels a row has (a missing or undefined target is masked, never a zero). AdamW,
learning rate halved when the validation loss stalls, early stopping, gradient norm
clipped at 1. A label enters training only once it was released before the fold year.
"""

import json
import math
import os
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch
from torch import nn

from multiverse_contracts.forecasting import EpochLog, ForecastTarget
from multiverse_forecast.data import Floats
from multiverse_forecast.probabilistic import RATIO_SCALE, from_target_space

QUANTILES = (0.1, 0.5, 0.9)
TARGETS = tuple(ForecastTarget)
HORIZONS = (1, 4, 8, 12, 20)
GROWTH_CHANNEL = 0
LOG_REVENUE_CHANNEL = 1


@dataclass
class Config:
    hidden: int = 64
    layers: int = 1
    dropout: float = 0.1
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    batch_size: int = 256
    max_epochs: int = 40
    patience: int = 4
    seed: int = 20261030
    threads: int = 8
    device: str = "auto"
    arch: str = "gru_attention"
    levels: tuple[float, ...] = QUANTILES

    def __post_init__(self) -> None:
        self.levels = tuple(self.levels)

    def plain(self) -> dict[str, object]:
        """Every field; the default levels stay out, so Stage 16 runs keep their ids."""
        values = asdict(self)
        if self.levels == QUANTILES:
            del values["levels"]
        return values

    def params(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.plain().items()}


def device_for(config: Config) -> torch.device:
    if config.device == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(config.device)


def seed_everything(config: Config) -> None:
    # cuBLAS is deterministic only with a fixed workspace; set before CUDA starts.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.manual_seed(config.seed)
    torch.cuda.manual_seed_all(config.seed)
    np.random.seed(config.seed % 2**32)
    torch.set_num_threads(config.threads)
    torch.use_deterministic_algorithms(True, warn_only=True)


def channel_transform(sequence: Floats) -> Floats:
    """Fixed transforms of the channels: growth as is, log revenue as is, ratios by asinh."""
    out = np.array(sequence, dtype=np.float64, copy=True)
    ratios = [c for c in range(out.shape[-1]) if c not in (GROWTH_CHANNEL, LOG_REVENUE_CHANNEL)]
    out[..., ratios] = np.arcsinh(out[..., ratios] / RATIO_SCALE)
    return out


@dataclass
class SequencePrep:
    """Mean and scale of each channel over its observed training values."""

    mean: Floats = field(default_factory=lambda: np.zeros(0))
    std: Floats = field(default_factory=lambda: np.zeros(0))

    def fit(self, values: Floats) -> "SequencePrep":
        flat = values.reshape(-1, values.shape[-1])
        with np.errstate(all="ignore"):
            self.mean = np.nan_to_num(np.nanmean(flat, axis=0))
            std = np.nan_to_num(np.nanstd(flat, axis=0))
        self.std = np.where(std > 0, std, 1.0)
        return self

    def transform(self, values: Floats) -> tuple[Floats, Floats]:
        mask = (~np.isnan(values)).astype(np.float64)
        scaled = np.nan_to_num((values - self.mean) / self.std)
        return scaled * mask, mask


class CausalConvolutions(nn.Module):  # type: ignore[misc,unused-ignore]
    """Residual causal convolutions: the state of a quarter sees only earlier quarters."""

    def __init__(self, hidden: int, layers: int, dropout: float, kernel: int = 3) -> None:
        super().__init__()
        self.kernel = kernel
        self.dilations = [2 ** (i % 4) for i in range(4 * layers)]
        self.convs = nn.ModuleList(
            nn.Conv1d(hidden, hidden, kernel, dilation=d) for d in self.dilations
        )
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, None]:
        h = x.transpose(1, 2)
        for conv, d in zip(self.convs, self.dilations, strict=True):
            padded = nn.functional.pad(h, ((self.kernel - 1) * d, 0))
            h = h + self.drop(torch.relu(conv(padded)))
        return h.transpose(1, 2), None


class TemporalModel(nn.Module):  # type: ignore[misc,unused-ignore]
    """An encoder over the quarters (GRU or causal convolutions), additive attention over
    its states, the last state and the static features, then an MLP head."""

    def __init__(self, channels: int, static: int, config: Config) -> None:
        super().__init__()
        hidden = config.hidden
        self.levels = config.levels
        self.embed = nn.Linear(2 * channels, hidden)
        self.gru: nn.Module
        if config.arch == "tcn":
            self.gru = CausalConvolutions(hidden, config.layers, config.dropout)
        else:
            self.gru = nn.GRU(
                hidden,
                hidden,
                num_layers=config.layers,
                batch_first=True,
                dropout=config.dropout if config.layers > 1 else 0.0,
            )
        self.score = nn.Sequential(nn.Linear(hidden, hidden), nn.Tanh(), nn.Linear(hidden, 1))
        self.static = nn.Sequential(nn.Linear(static, hidden), nn.ReLU())
        self.head = nn.Sequential(
            nn.Linear(3 * hidden, hidden),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(hidden, len(TARGETS) * len(HORIZONS) * len(config.levels)),
        )

    def forward(
        self, values: torch.Tensor, mask: torch.Tensor, static: torch.Tensor
    ) -> torch.Tensor:
        states, _ = self.gru(torch.relu(self.embed(torch.cat([values, mask], dim=-1))))
        observed = mask.amax(dim=-1) > 0
        scores = self.score(states).squeeze(-1).masked_fill(~observed, -1e9)
        weights = torch.softmax(scores, dim=1)
        context = (weights.unsqueeze(-1) * states).sum(dim=1)
        joined = torch.cat([context, states[:, -1], self.static(static)], dim=-1)
        raw = self.head(joined).view(-1, len(TARGETS), len(HORIZONS), len(self.levels))
        return quantiles(raw)


GruAttention = TemporalModel


def quantiles(raw: torch.Tensor) -> torch.Tensor:
    """Ordered quantiles in each target's space: smooth transforms, no clamps."""
    middle = raw.shape[-1] // 2
    median = raw[..., middle : middle + 1]
    below = nn.functional.softplus(raw[..., :middle].flip(-1)).cumsum(dim=-1).flip(-1)
    above = nn.functional.softplus(raw[..., middle + 1 :]).cumsum(dim=-1)
    q = torch.cat([median - below, median, median + above], dim=-1)
    growth = TARGETS.index(ForecastTarget.REVENUE_GROWTH)
    debt = TARGETS.index(ForecastTarget.DEBT_TO_EBITDA)
    parts = [q[:, t] for t in range(len(TARGETS))]
    parts[growth] = 2 * torch.tanh(parts[growth])
    parts[debt] = nn.functional.softplus(parts[debt])
    return torch.stack(parts, dim=1)


def pinball(
    q: torch.Tensor,
    labels: torch.Tensor,
    present: torch.Tensor,
    levels: tuple[float, ...] = QUANTILES,
) -> torch.Tensor:
    """Pinball loss per (target, horizon), averaged over present labels, then over pairs."""
    taus = torch.tensor(levels, dtype=q.dtype, device=q.device)
    diff = labels.unsqueeze(-1) - q
    loss = torch.maximum(taus * diff, (taus - 1) * diff).sum(dim=-1)
    counts = present.sum(dim=0)
    per_pair = (loss * present).sum(dim=0) / counts.clamp(min=1)
    used = counts > 0
    return per_pair[used].mean() if used.any() else per_pair.sum() * 0


@dataclass
class Arrays:
    values: Floats
    mask: Floats
    static: Floats
    labels: Floats
    """Targets in their training space; NaN where missing, undefined or not yet released."""

    def on(self, device: torch.device) -> "OnDevice":
        """All rows as tensors on one device, once: batches are then index lookups."""
        arrays = (
            self.values,
            self.mask,
            self.static,
            np.nan_to_num(self.labels),
            ~np.isnan(self.labels),
        )
        return OnDevice(
            tuple(torch.tensor(a, dtype=torch.float32, device=device) for a in arrays), device
        )


@dataclass
class OnDevice:
    arrays: tuple[torch.Tensor, ...]
    device: torch.device

    def batch(self, rows: np.ndarray) -> tuple[torch.Tensor, ...]:
        index = torch.as_tensor(rows, dtype=torch.long, device=self.device)
        return tuple(a.index_select(0, index) for a in self.arrays)


@dataclass
class Trained:
    model: GruAttention
    epochs: list[EpochLog]
    best_epoch: int


def _loss(model: GruAttention, batch: tuple[torch.Tensor, ...]) -> torch.Tensor:
    values, mask, static, labels, present = batch
    return pinball(model(values, mask, static), labels, present, model.levels)


def evaluate_loss(model: GruAttention, data: OnDevice, rows: np.ndarray, config: Config) -> float:
    model.eval()
    total, weight = 0.0, 0
    with torch.no_grad():
        for start in range(0, rows.size, config.batch_size):
            part = rows[start : start + config.batch_size]
            total += float(_loss(model, data.batch(part))) * part.size
            weight += part.size
    return total / max(weight, 1)


@dataclass
class Progress:
    """A training between two epochs: everything it needs to go on."""

    model: GruAttention
    optimizer: torch.optim.Optimizer
    scheduler: torch.optim.lr_scheduler.ReduceLROnPlateau
    rng: np.random.Generator
    epochs: list[EpochLog] = field(default_factory=list)
    best: float = math.inf
    best_epoch: int = 1
    best_state: dict[str, torch.Tensor] | None = None
    stale: int = 0


def begin(data: Arrays, config: Config) -> tuple[Progress, OnDevice]:
    seed_everything(config)
    device = device_for(config)
    model = GruAttention(data.values.shape[-1], data.static.shape[-1], config).to(device)
    placed = data.on(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=1)
    return Progress(model, optimizer, scheduler, np.random.default_rng(config.seed)), placed


def step(
    progress: Progress,
    placed: OnDevice,
    train_rows: np.ndarray,
    valid_rows: np.ndarray,
    config: Config,
) -> bool:
    """One epoch; False when the training is over."""
    model, optimizer = progress.model, progress.optimizer
    epoch = len(progress.epochs) + 1
    started = time.perf_counter()
    model.train()
    order = progress.rng.permutation(train_rows)
    total, weight = 0.0, 0
    for start in range(0, order.size, config.batch_size):
        part = order[start : start + config.batch_size]
        loss = _loss(model, placed.batch(part))
        if not torch.isfinite(loss):
            raise FloatingPointError(f"loss is not finite at epoch {epoch}")
        optimizer.zero_grad()
        loss.backward()  # type: ignore[no-untyped-call,unused-ignore]
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total += float(loss.detach()) * part.size
        weight += part.size
    validation = evaluate_loss(model, placed, valid_rows, config)
    progress.scheduler.step(validation)
    progress.epochs.append(
        EpochLog(
            epoch=epoch,
            train_loss=total / weight,
            validation_loss=validation,
            learning_rate=float(optimizer.param_groups[0]["lr"]),
            seconds=time.perf_counter() - started,
        )
    )
    if validation < progress.best:
        progress.best, progress.best_epoch, progress.stale = validation, epoch, 0
        progress.best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    else:
        progress.stale += 1
    return progress.stale < config.patience and epoch < config.max_epochs


def finished(progress: Progress) -> Trained:
    if progress.best_state is not None:
        progress.model.load_state_dict(progress.best_state)
    return Trained(progress.model, progress.epochs, progress.best_epoch)


def train(data: Arrays, train_rows: np.ndarray, valid_rows: np.ndarray, config: Config) -> Trained:
    progress, placed = begin(data, config)
    while step(progress, placed, train_rows, valid_rows, config):
        pass
    return finished(progress)


def predict(
    model: GruAttention,
    data: Arrays,
    rows: np.ndarray,
    config: Config,
    *,
    target_space: bool = False,
) -> Floats:
    """Quantiles [rows, targets, horizons, levels], in each target's own units unless asked
    for its training space."""
    placed = data.on(next(model.parameters()).device)
    model.eval()
    parts = []
    with torch.no_grad():
        for start in range(0, rows.size, config.batch_size):
            part = rows[start : start + config.batch_size]
            values, mask, static, _, _ = placed.batch(part)
            parts.append(model(values, mask, static).cpu().numpy().astype(np.float64))
    shape = (0, len(TARGETS), len(HORIZONS), len(config.levels))
    q = np.concatenate(parts) if parts else np.zeros(shape)
    if target_space:
        return q
    for t, target in enumerate(TARGETS):
        q[:, t] = from_target_space(target, q[:, t])
    return q


def save_checkpoint(
    path: Path, model: GruAttention, config: Config, prep: dict[str, Sequence[float]], epoch: int
) -> None:
    """``torch.save`` of plain tensors and lists only: loadable with ``weights_only=True``."""
    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": json.dumps(config.plain()),
            "prep": json.dumps(prep),
            "epoch": epoch,
            "shape": [model.embed.in_features // 2, model.static[0].in_features],
        },
        path,
    )


def load_checkpoint(path: Path) -> tuple[GruAttention, Config, dict[str, list[float]]]:
    blob = torch.load(path, map_location="cpu", weights_only=True)
    config = Config(**json.loads(blob["config"]))
    channels, static = blob["shape"]
    model = GruAttention(channels, static, config)
    model.load_state_dict(blob["state_dict"])
    return model, config, json.loads(blob["prep"])
