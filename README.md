# MULTIVERSE — Financial Parallel Universe Engine

*What if business took another path?*

MULTIVERSE is a research platform for counterfactual corporate scenarios. An analyst picks a company, a historical cutoff date and a precisely defined management decision (R&D, restructuring, M&A, divestiture, CAPEX, refinancing). The platform compares probabilistic scenario paths against a baseline for revenue, EBITDA, FCF, net debt and enterprise value. Every number shows where it came from, what was known at the cutoff, and what kind of uncertainty it carries.

## Scientific limitations (read first)

- **Scenarios are not proven history.** A counterfactual such as "this company without that acquisition" has no observed ground truth. Results are conditional on stated assumptions.
- **Forecasts are not causal effects.** Predictive accuracy does not validate the effect of a decision. A result is labelled causal only after documented identification diagnostics.
- **Intervals are model quantiles** until their coverage is measured on held-out companies and dates.
- **No investment advice,** no share price prediction, no "fair market value".
- **Current status: Stage 14 (Gate B dataset audit) accepted; with the owner's decisions D-10, D-11 and D-12 the data is now acquired and Gate B passes with warnings on a universe of 1000 companies (review).** The Data Catalog describes the official sources (SEC EDGAR, FRED/ALFRED, ECB, World Bank). The SEC bulk files were downloaded into a local, immutable archive (`var/raw`, never committed), and a universe of 1000 US companies was drawn from them by written rules and a seed, stratified by SIC division and keeping companies that later deregistered (347 of 1000; `data/universe/sec-1000-20261030.json`). Their filings are normalized into canonical quarterly values with full lineage and placed in a point-in-time warehouse that answers what was public at any cutoff, with reproducible hashed snapshots (`var/data`, never committed). 18 macro series (FRED/ALFRED with vintages, ECB, World Bank) are joined with company quarters by the moment each value was published. The Gate B audit counts 17 508 usable examples at 12 quarters of history and a 4-quarter horizon from 899 companies, passes the leakage proof and 10 manual reconciliations with the filings, and lists 14 warnings about the real data in its data card. The app shows none of it. The Universe Explorer, Company Dossier, Decision Builder, Timeline Explorer, Universe Compare and Research Notebook work on clearly labelled fictional companies and mock results; saved scenarios stay in the browser of one device. There is no trained model or simulation yet. Nothing in this repository claims measured accuracy.

## Status

| Stage | Scope | Status |
|---|---|---|
| 00 | Master orchestrator briefing, scientific risks | Accepted |
| 01 | Product requirements (`docs/product/`) | Accepted |
| 02 | Monorepo foundation, contracts, quality gates, ADRs | Accepted |
| 03 | Design system and application shell (`apps/web`) | Accepted |
| 04 | Company explorer and dossier on synthetic fixtures | Accepted |
| 05 | Decision builder: six decision types, validation, intervention catalog | Accepted |
| 06 | Timeline charts and scenario comparison on mock results | Accepted |
| 07 | Research notebook: saved scenarios, revisions, reports, on this device only | Accepted |
| 08 | Gate A: frontend audit, V1 release note (`docs/releases/`) | Accepted |
| 09 | Source policy and Data Catalog: licences, rate limits, risk register, acquisition plan (metadata only) | Accepted |
| 10 | SEC raw ingestion: immutable archive, metadata index, audit manifests, sample of ten companies (`pipelines/`) | Accepted |
| 11 | XBRL normalization: concept map, quarters, revisions, quality flags, manual reconciliation of three companies | Accepted |
| 12 | Point-in-time warehouse: as-of values, quarterly panel with feature masks, hashed snapshots, chronology alerts, coverage dashboard | Accepted |
| 13 | Macro vintages: series registry, availability timestamps, as-of join with company quarters, timestamp QA | Accepted |
| 14 | Gate B: dataset audit, usable examples, data card, coverage report, manifest with hash, 10 manual reconciliations (verdict blocked) | Accepted |
| 14b | Data acquisition (D-10, D-11, D-12): SEC bulk files, universe of 1000 companies, real macro store, PIT warehouse at scale, Gate B passed with warnings | Review |
| 15–26 | ML → causal → finance → publication | Planned |

## Repository layout

```text
apps/web/              Next.js web app: design system, shell, explorer, dossier, decision builder, timelines, compare, notebook, data catalog
services/api/          FastAPI HTTP API — composition root: multiverse_api.main:create_app
services/worker/       Background jobs: simulation and training (queue in Stage 18)
packages/contracts/    Shared contracts — single source of truth (ADR-0008)
  python/              Pydantic models (the source)
  schemas/             Generated JSON Schema
  ts/                  Generated TypeScript types (@multiverse/contracts)
  fixtures/            Valid and invalid examples shared by tests; demo/ holds the synthetic companies
  catalog/             Generated intervention catalog (ADR-0013) and source catalog: licences, limits, risks, plan (ADR-0016)
  fixtures/mock/       Generated mock scenario results for the charts (ADR-0014), not forecasts
  fixtures/notebook/   A valid notebook export shared by the Python and web tests (ADR-0015)
packages/config/       Validated settings and environment profiles (ADR-0010)
packages/finance/      Pure financial formulas (Stage 21, 23)
packages/causal/       Causal research tools (Stage 20)
packages/forecast/     Baselines and temporal neural nets; ML libraries are optional extras
pipelines/             SEC raw ingestion (10), XBRL normalization (11), point-in-time warehouse (12), macro vintages (13)
data/schemas/          Normalized and point-in-time data definitions (Stage 11–12)
configs/               Model and infrastructure parameters
notebooks/research/    Research notebooks
infra/                 Containers and deployment (later)
tests/                 Cross-module tests: smoke, contract (later integration, backtesting, e2e)
docs/                  Product requirements, ADRs, engineering conventions, stage reports
```

Module dependencies are enforced, not just documented: services → domain packages → base (`contracts`, `config`), siblings independent, and the API may not import forecasting, causal or pipeline code (ADR-0003, ADR-0009).

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| uv | ≥ 0.8 (tested 0.11) | Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` · Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | ≥ 22 (tested 24) | <https://nodejs.org> (npm is included) |
| Git | any recent | <https://git-scm.com> |

You do not need to install Python yourself: uv downloads Python 3.12 automatically (pinned in `.python-version`).

## Quick start

The same commands work in Windows PowerShell and Linux / macOS bash. Run them from the repository root.

```bash
uv sync --all-packages
```

```bash
npm install
```

The browser tests need Chromium once per machine:

```bash
npx --workspace @multiverse/web playwright install chromium
```

```bash
npm run check
```

`npm run check` is the full quality gate: Python, TypeScript, contracts drift, then a production build of the web app and the browser tests. It ends with Playwright's `passed` summary when everything passes.

Start the web app and open <http://localhost:3000>:

```bash
npm run dev:web
```

Optional local configuration (only needed to change defaults):

```bash
cp .env.example .env
```

On Windows PowerShell use `Copy-Item .env.example .env` instead.

Start the API and open <http://127.0.0.1:8000/api/v1/health> (interactive docs at `/api/docs`):

```bash
npm run dev:api
```

## Commands

| Command | What it does |
|---|---|
| `npm run check` | Full gate: Python lint, format, mypy strict, module boundaries, tests; TypeScript lint, format, typecheck, tests; contracts drift |
| `npm run check:py` | Python part of the gate |
| `npm run check:ts` | TypeScript part of the gate |
| `npm test` | All tests (pytest + vitest) |
| `npm run format` | Auto-format Python and TypeScript |
| `npm run contracts:gen` | Regenerate JSON Schema, demo fixtures, the intervention and source catalogs, mock results and TypeScript types after changing `packages/contracts/python` |
| `npm run contracts:check` | Fail if generated contracts are stale |
| `npm run check:web` | Production build of the web app and Playwright tests at 1440, 768 and 390 px |
| `npm run dev:web` | Run the web app with hot reload on localhost:3000 |
| `npm run build:web` | Production build of the web app |
| `npm run test:e2e` | Browser tests (after `build:web`): overflow, axe WCAG 2.2, keyboard, dialog, drawer, links |
| `npm run dev:api` | Run the API with auto-reload on 127.0.0.1:8000 |
| `npm run worker` | Run the worker (validates configuration; queue arrives in Stage 18) |
| `uv sync --all-packages --extra boosting` | Add scikit-learn and LightGBM (Stage 15) |
| `uv sync --all-packages --extra ml` | Add PyTorch (Stage 16) |

## Configuration

Settings come from `MULTIVERSE_*` environment variables or `.env` and are validated at startup (ADR-0010). Profiles: `local` (default), `test`, `ci`, `production`. Safe defaults: network downloads are off and the cloud spending limit is `0`. See `.env.example`. Never commit `.env`.

## Documentation

- Product requirements: `docs/product/` (PRD, personas, user stories, scope V0–V4, risks, metric definitions)
- Architecture decisions: `docs/adr/`
- Engineering conventions: `docs/engineering/conventions.md`
- Stage reports: `docs/stages/`
- Release notes: `docs/releases/`
- Original specification: `../MULTIVERSE_Documentation_Kit/`

## Author

Maxim Leshchenko — Data Science, Protection & Security, Thomas More (Belgium).

License: not chosen yet.
