# Cross-cutting tests

Unit tests live next to their module (`packages/*/tests`, `services/*/tests`). This folder holds tests that span modules (`docs/11`):

| Folder | What | Since |
|---|---|---|
| `smoke/` | Every module imports, versions agree, no secrets in the repository | Stage 02 |
| `contract/` | Generated contract artifacts match their single source | Stage 02 |
| `integration/` | Source → parser → storage → PIT view → API; job → worker → artifact | Stage 10+ |
| `backtesting/` | Rolling-origin and point-in-time leakage tests | Stage 12+ |
| `apps/web/e2e/` | Browser tests with Playwright, next to the web app they start | Stage 03 |

Run everything with `npm run check`, or only Python tests with `uv run pytest`.
