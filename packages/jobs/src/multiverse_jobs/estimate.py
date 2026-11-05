"""What a job may cost, before anyone approves it (docs/13: dry run before training).

Rates are measured on this project's own trainings (Stages 16 and 17): median seconds of
one epoch per 10 000 training rows. They are estimates, shown as such. A job on a rented
GPU states its hourly rate; on the owner's machine the rate is zero.
"""

from multiverse_contracts.jobs import JobEstimate, JobRequest

SECONDS_PER_10K_ROWS = {"cpu": 1.44, "cuda": 0.65}
TYPICAL_ROWS = 19_060
EPOCH_SHARE = 0.35
"""Trainings stopped early after about a third of 80 allowed epochs (11-31 of 80)."""
DEFAULT_HIDDEN = 64
PEAK_VRAM_MB = 224.0
"""Peak reserved by PyTorch with all rows on the device, measured on the RTX 4070 Laptop GPU;
the CUDA context itself comes on top."""
BYTES_PER_PARAMETER = 4
MAX_RUNTIME_SECONDS = 4 * 3600
"""The longest job that needs no ``overnight``: nothing runs all night by accident."""


def parameters(request: JobRequest) -> int:
    """Rough size of the network, from the sizes measured on Stage 16."""
    values = {p.name: p.value for p in request.params}
    hidden = int(values.get("hidden", DEFAULT_HIDDEN))
    layers = int(values.get("layers", 1))
    per_layer = 12 * hidden * hidden if request.model == "tcn" else 6 * hidden * hidden
    return layers * per_layer + 8 * hidden * hidden + 300 * hidden


def estimate(request: JobRequest, rows: int = TYPICAL_ROWS) -> JobEstimate:
    device = "cpu" if request.device == "cpu" else "cuda"
    epochs = max(1.0, EPOCH_SHARE * request.max_epochs)
    seconds = epochs * rows / 10_000 * SECONDS_PER_10K_ROWS[device]
    size_mb = parameters(request) * BYTES_PER_PARAMETER / 1e6
    return JobEstimate(
        seconds=round(seconds, 1),
        vram_mb=0.0 if device == "cpu" else round(PEAK_VRAM_MB + 4 * size_mb, 1),
        disk_mb=round(2 * 4 * size_mb + 1, 1),
        cost_usd=round(seconds / 3600 * request.rate_usd_per_hour, 4),
        basis=(
            f"{SECONDS_PER_10K_ROWS[device]} s per epoch per 10 000 rows on {device}, measured "
            f"on Stages 16 and 17; about {epochs:.0f} of {request.max_epochs} epochs with early "
            f"stopping; {rows} rows"
        ),
    )


def refusals(request: JobRequest) -> list[str]:
    """Why a request may not even wait in the queue."""
    found: list[str] = []
    if request.max_runtime_seconds > MAX_RUNTIME_SECONDS and not request.overnight:
        found.append(
            f"max_runtime_seconds above {MAX_RUNTIME_SECONDS} needs overnight: true, on purpose"
        )
    if request.rate_usd_per_hour > 0 and request.spend_limit_usd == 0:
        found.append("a paid job needs a spend limit above zero")
    return found
