# multiverse-worker

Background worker for training jobs (Stage 18, ADR-0026): takes approved jobs from the durable queue in `multiverse_jobs`, keeps their lease with heartbeats, checks budgets at every safe point, and ends every job in a named state. It exits when the queue is empty, so nothing trains overnight by accident.

```bash
uv run multiverse-worker run
```

```bash
uv run multiverse-worker status
```

Training needs the `ml` extra (`uv sync --all-packages --extra ml`). Simulation jobs arrive with Stage 22.
