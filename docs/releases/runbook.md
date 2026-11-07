# Maintenance runbook

For the owner of a local installation. Commands run from the repository root; Windows PowerShell and bash take the same commands unless marked.

## Start and stop

```bash
npm run app
```

API on 127.0.0.1:8000, worker, site on <http://localhost:3000>. Ctrl+C stops all three. If the site already runs on port 3000, only the API and the worker start. Jobs survive a stop: the worker continues them from their checkpoints at the next start.

Check the queue:

```bash
uv run python -m multiverse_worker.main status
```

## Health and monitoring hooks

| Hook | What it tells |
|---|---|
| `GET /api/v1/health` | The API answers, with its profile and contracts version |
| Job heartbeats | Each running job writes a heartbeat; the Models screen flags a job silent for 60 s |
| `GET /api/v1/audit` (admin) | Every protected read and action, without addresses or tokens, kept 90 days |
| CI on GitHub | Lint, types, tests, contracts drift, secret scan and dependency audit on every push |

## Before any upgrade: back up

```bash
uv run python -m multiverse_worker.main backup ../multiverse-backup-YYYYMMDD
```

```bash
uv run python -m multiverse_worker.main verify ../multiverse-backup-YYYYMMDD
```

On 2026-11-07 this took 24 s for 37 files and 10 jobs. Backups hold no `.env`.

## Upgrade and roll back

1. Back up and verify, as above.
2. `git pull`, then `uv sync --all-packages` and `npm install`.
3. `npm run check` must pass before the app starts again.
4. Contracts are versioned (`packages/contracts/python/src/multiverse_contracts/version.py`). A stored file of an older version that no longer validates is refused, never silently converted.
5. To roll back: `git checkout <previous commit>`, `uv sync --all-packages`, `npm install`, then restore the backup into an empty data folder and point `MULTIVERSE_DATA_DIR` at it:

```bash
uv run python -m multiverse_worker.main restore ../multiverse-backup-YYYYMMDD ../multiverse-data-restored
```

## Refresh data and models

Each step writes new hashed folders and never overwrites the last ones. Downloads stay off in `.env` (`MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=false`); set it to true for one command, and only within the owner's decisions on sources.

| Step | Command | Time measured on 2026-11-06 |
|---|---|---|
| SEC bulk files | `uv run python -m multiverse_pipelines.sec bulk companyfacts-zip` and `submissions-zip` | — |
| Ranking | `uv run python -m multiverse_pipelines.sec top --size 500` | — |
| Warehouse | `uv run python -m multiverse_pipelines.pit --db <file> build --universe <file>` | 23.5 min, 1 429 companies |
| Dataset and sequences | `uv run python -m multiverse_pipelines.forecastset build …`, then `sequences` | 8.4 and 6.9 min |
| Baselines and network | `uv run python -m multiverse_forecast benchmark …`, then `neural-benchmark … --device cuda` | 11.5 and 63.4 min |
| Live forecast | `uv run python -m multiverse_forecast live --dataset <folder> --device cuda` | 8.9 min |
| Companies and cases | `uv run python -m multiverse_simulation companies …` | 7.6 min |

Training on the GPU is a cost the owner approves; cloud spending stays at zero (`cloud_spend_limit_usd = 0`). New training on FRED series is refused in code (LIC-001).

## Reports

- A finished run gets its report from the worker. Runs made before Stage 25: `uv run python -m multiverse_worker.main reports`.
- Prove a report: `uv run python -m multiverse_simulation replay --manifest <folder>/manifest.json --case <case file>`.

## Tokens (only when the API leaves the loopback)

```bash
uv run python -m multiverse_api.tokens --help
```

Tokens are stored as SHA-256 hashes with a role and an expiry. Never commit `.env` or a token. Read [`docs/security/README.md`](../security/README.md) before exposing the API: TLS and a browser login are required first (OPS-001, OPS-002).

## When something breaks

| Symptom | First step |
|---|---|
| The site says the engine is not running | `npm run app`; check that port 8000 is free |
| A job is silent | `status`; stop it from the Models page; it resumes from its last checkpoint |
| A report does not replay | Keep the folder, compare the three SHA-256 values in its manifest, and open an issue with the report id |
| The gate fails | Run the failing suite alone; a test that passes alone and fails under load is recorded as flaky in the stage report |
| A secret was committed | Rotate it first, then follow [incident response](../security/incident-response.md) |
