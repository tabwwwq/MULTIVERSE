# multiverse-pipelines

Data pipelines for SEC, FRED, ECB and World Bank (`docs/04`). They read the source catalog of Stage 09 (`packages/contracts/catalog/sources.json`, ADR-0016) and build up in stages:

| Stage | Pipeline | Status |
|---|---|---|
| 10 | SEC raw ingestion: Submissions API, Company Facts API, bulk ZIPs (ADR-0017) | **Done** |
| 11 | XBRL normalization: canonical values with lineage, revisions and quality (ADR-0018) | **Done** |
| 12 | Point-in-time warehouse: as-of values, quarterly panel with masks, hashed snapshots (ADR-0019) | **Done** |
| 13 | Macro vintages: FRED/ALFRED, ECB, World Bank registry, availability, as-of join (ADR-0020); real store since D-11 and D-12 | **Done** |
| 14 | Gate B: dataset audit, usable examples, data card, coverage report, manifest with hash (ADR-0021) | **Done** (blocked on the sample) |
| 14b | Data acquisition: SEC bulk files and a universe of 1000 companies (ADR-0022), real macro store, warehouse at scale; Gate B passed with warnings | **Done** |

Rules:

- No network access unless `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true` **and** the owner approved the source in the catalog.
- SEC fair access: a declared User-Agent with a contact email, 2 requests per second for the whole process.
- Raw files live in `var/raw/` and are never committed.

## SEC raw ingestion

`.env` (ignored by git) holds the contact and keeps downloads off:

```
MULTIVERSE_SEC_USER_AGENT="MULTIVERSE research name@example.com"
MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=false
MULTIVERSE_RAW_DIR=var/raw
MULTIVERSE_RAW_BUDGET_MB=200
```

Commands, run from the repository root:

| Command | Network | What it does |
|---|---|---|
| `uv run python -m multiverse_pipelines.sec status` | no | Switch, User-Agent present, owner decision, archive use against the budget |
| `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true uv run python -m multiverse_pipelines.sec sample` | yes | Submissions (with the older-filing pages they list) and company facts of the ten catalog candidates; `--cik 97476` (repeatable) for others; `--max-age-hours 12` reuses files confirmed recently |
| `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true uv run python -m multiverse_pipelines.sec probe companyfacts-zip` | one HEAD | Size and Last-Modified of a bulk file (`companyfacts-zip`, `submissions-zip`, `fsds --quarter 2024q1`) |
| `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true uv run python -m multiverse_pipelines.sec bulk fsds --quarter 2024q1 --max-mb 150` | yes | One bulk ZIP after a HEAD shows it fits; refused until the catalog holds a `bulk` approval (decision D-10) |
| `uv run python -m multiverse_pipelines.sec verify` | no | Re-hashes every archived file; finds changed, missing, writable and unknown files |
| `uv run python -m multiverse_pipelines.sec coverage [--json]` | no | What the archived sample holds per candidate: filings by form, taxonomies, periods per V2 metric |
| `uv run python -m multiverse_pipelines.sec universe [--size 1000] [--seed 20261030] [--no-extract]` | no | Draws the study universe from the archived bulk ZIPs by written rules and a seed (ADR-0022), writes `data/universe/sec-<size>-<seed>.json` and copies the chosen companies' files out of the ZIPs into the archive; needs the bulk approval (D-10) |

On Windows PowerShell, set the switch for one command with `$env:MULTIVERSE_ALLOW_NETWORK_DOWNLOADS='true'; uv run python -m multiverse_pipelines.sec sample; Remove-Item Env:MULTIVERSE_ALLOW_NETWORK_DOWNLOADS`.

Exit codes: 0 done, 1 some files failed, 2 refused or aborted (403, budget, permission), 3 the archive has problems.

### Archive layout

```
var/raw/sec/
  submissions/CIK0000097476/<sha256>.json                    company metadata and latest filings
  submissions/CIK0000097476/submissions-001/<sha256>.json    older filings
  companyfacts/CIK0000097476/<sha256>.json                   every XBRL fact with accn and filed date
  financial-statement-data-sets/2024q1/<sha256>.zip          bulk only
  index.jsonl                                                one RawObject per file (metadata table)
  runs/<run_id>.json                                         one RunManifest per command (audit)
  tmp/*.part                                                 unfinished downloads, removed at the next start
```

Files are read-only and named by their SHA-256. The same bytes are never stored twice, and a changed file becomes a new object next to the old one.

### Identifiers and taxonomies

- **CIK:** the API uses ten digits with leading zeros (`CIK0000097476.json`); Archives paths use the plain number (`/edgar/data/97476/`). Submissions JSON writes the CIK as a string without zeros, company facts as an integer. `multiverse_pipelines.sec.cik` handles all three forms.
- **Tickers change and are reused.** They are an observation with a date (`tickers` in submissions), never a key. Celgene, acquired in 2019, has no ticker today.
- **US-GAAP and IFRS:** domestic filers report in `us-gaap` on 10-K and 10-Q. Foreign private issuers file 20-F or 40-F and may report in `ifrs-full`. The V2 universe is domestic US-GAAP filers; the coverage report counts taxonomies and foreign forms instead of assuming them.
- **Access:** EDGAR data needs no account. EDGAR Next filer accounts are for submitting filings and are never used here. The only identity sent is the User-Agent.

## XBRL normalization

Reads only the local raw archive; no network. Run from the repository root:

| Command | What it does |
|---|---|
| `uv run python -m multiverse_pipelines.xbrl normalize` | All archived candidates (or `--cik`, repeatable) into `var/data/normalized/sec/` (`--out` for another folder) |
| `uv run python -m multiverse_pipelines.xbrl show --cik 97476 --fiscal-year 2025 [--revision original]` | One company and year as a table: values in millions with the method of each, for reconciliation with the filings |

Output (never committed):

| File | Content |
|---|---|
| `values.jsonl` | One `NormalizedValue` (contracts 0.8.0) per line: the reference format with full lineage |
| `values.csv` | The same rows flattened; `sources` and `alternatives` as text |
| `schema.json` | JSON Schema of the row |
| `coverage.json`, `coverage.md` | Valid quarters in the last 8 / 20 / 40 per company and metric, concepts and methods used (data card) |
| `manifest.json` | Input raw files with SHA-256, contracts version, row counts |

One row is one metric of one company for one fiscal period (Q1 to Q4, FY) under one revision:

- `original`: each fact as first filed;
- `latest`: as last filed, amendments and restatements included.

Each row names its concept, its method and the source facts with their signs. It also names the accession and date of the filing that made it knowable, and the other candidate concepts with their differences. Missing values carry a reason, never zero.

Metrics: `revenue`, `cogs`, `operating_income`, `net_income`, `rnd`, `depreciation_amortization`, `cfo`, `capex`, `cash`, `long_term_debt`, `long_term_debt_noncurrent`, `debt_current`, `shares_diluted`, `shares_outstanding`; calculated `free_cash_flow` (CFO − capex) and `ebitda` (operating income + D&A, not adjusted). The concept map with relations is `multiverse_pipelines/xbrl/concepts.py`.

A latest derived value that combines a revised part with a part filed before that revision (a restated year minus nine months nobody restated) carries the flag `mixed_vintage` (Stage 12).

## Point-in-time warehouse

Reads only the local raw archive (company facts and submissions with their paged files); no network. Run from the repository root:

| Command | What it does |
|---|---|
| `uv run python -m multiverse_pipelines.pit build [--universe data/universe/sec-1000-20261030.json] [--workers 12]` | The catalog candidates, `--cik` or a universe into `var/data/pit/warehouse.sqlite`; companies run in parallel and stream into the file one at a time; payloads are zlib-compressed with a dictionary stored in the file (1000 companies: 3.86 million value intervals, 1.3 GB, 14 minutes on 12 workers) |
| `... pit as-of --cik 97476 --metric revenue --at 2021-12-31 [--view vintage\|original\|latest]` | One company and metric as known at a moment |
| `... pit history --cik 48898 --metric revenue --fiscal-year 2019 --period FY` | Every answer one period had: its corrections over time |
| `... pit entity --cik 816284 --at 2020-06-30` | Name, ticker, exchange, SIC code and status as known at a moment |
| `... pit snapshot --cutoff 2021-12-31 [--quarters 20] [--view vintage\|original]` | The as-of panel, hashed, with features and lineage, into `var/data/pit/snapshots/<id>/` |
| `... pit coverage --cutoff 2025-12-31` | Coverage dashboard (`coverage.html`, `.md`, `.json`) into `var/data/pit/coverage/` |
| `... pit alerts [--severity warning]` | Broken chronology alerts |
| `... pit leakage-check --cutoff 2021-12-31` | Rebuilds from only what was public at the cutoff and compares the snapshot hash with the full archive (exit 1 if they differ) |

A cutoff given as a date is the end of that day in US Eastern time (EDGAR's clock); a time needs its offset (`2021-12-31T16:00-05:00`).

When a filing became public: its EDGAR acceptance time (UTC in the submissions file), but never before the start of its filing date. An evening filing dated the next business day belongs to that day, so a cutoff of 31 December never sees a filing dated in January. When only the date is known (1990s filings, filings missing from the index), the end of that day.

Each normalized value is stored with the interval of knowledge time during which it was the current answer (`PitValue`: `known_from`, `known_to`, why it changed, when each source filing was public). The Stage 11 normalizer runs again at every moment a filing became public, on exactly the facts public then, so an as-of query equals normalizing what was public at the cutoff: fiscal calendar, concept of the year, currency and derived quarters included. The current fiscal year, which has no 10-K yet, is placed as a provisional year from its 10-Qs. Facts that end after their own filing (estimates) never enter a view.

Views:

- `vintage`: as last filed before the cutoff, the default for features;
- `original`: as first filed before the cutoff, to compare forecasts with the first release;
- `latest`: as known today. Hindsight, for studying revisions only; panels and snapshots refuse it.

The panel (`PanelCell`) has a cell for every company, each of the last N calendar quarters ended at the cutoff and each metric. A fiscal quarter belongs to the nearest calendar quarter end (a quarter ending 2 January is the fourth quarter). The mask is true only for `observed` and `derived` cells. Every other state says why the cell is empty and is never zero:

| State | Meaning |
|---|---|
| `not_yet_filed` | The quarter ended, its 10-Q or 10-K was not public yet |
| `not_reported` | The report was public, without this metric |
| `blocked` | Withheld: conflicting values in one filing |
| `inactive` | A Form 15 before the quarter ended, no periodic report after it, and the report for the first quarter after the Form 15 overdue (over 90 days). Until then `not_yet_filed`: a Form 15 can cover one class of securities only |
| `not_covered` | Before the first XBRL report |

Features (`ttm_<flow>`, `yoy_<flow>`) are computed from panel cells only, never from the warehouse, so they cannot see more than the panel; the mask propagates.

Snapshot folder (never committed):

| File | Content |
|---|---|
| `snapshot.jsonl` | Header, each company as of the cutoff, every cell: canonical JSON lines; its SHA-256 names the snapshot (`pit-<date>-<12 hex>`) |
| `panel.csv`, `features.csv` | The cells and the features flattened |
| `lineage.jsonl` | Each value: source facts, accession, when public, filing URL on sec.gov, raw file SHA-256 |
| `manifest.json` | `PitSnapshotManifest`: cutoff, view, window, counts per state, inputs with SHA-256, versions, build time (not hashed) |

Identity over time: names follow `formerNames` with their dates. Tickers, exchanges and SIC codes are current values in the submissions file; they apply from the moment they were observed and never backwards, so an old cutoff sees no ticker or sector rather than today's. Their history per filing is in the Financial Statement Data Sets (decision D-10).

## Macro vintages

No download runs without the owner's decisions: D-11 (the owner registers the FRED key and puts it into `.env` as `MULTIVERSE_FRED_API_KEY`) and D-12 (ECB and World Bank). Until then everything runs on SYNTHETIC documents in the shape of the real responses, kept apart from archived data.

| Command | What it does |
|---|---|
| `uv run python -m multiverse_pipelines.macro status` | Per source: owner decision, FRED key set or not (never its value), stored series |
| `... macro fetch --source fred\|ecb\|worldbank [--series ID]` | Download into `var/raw/fred`, `ecb`, `worldbank` (20 MB); refused unless downloads are on for this command, the owner approved the source and, for FRED, the key is set |
| `... macro build` | Archived files into `var/data/macro/macro.sqlite`; sources without files are reported, not fatal |
| `... macro load-synthetic [--until 2026-10-28]` | SYNTHETIC documents into `var/data/macro/macro-synthetic.sqlite` |
| `... macro as-of --series fred:CPIAUCSL --at 2021-12-31 [--synthetic]` | One series as available at a moment |
| `... macro qa [--synthetic]` | Series metadata, coverage and timestamp QA into `var/data/macro/qa/` |
| `... macro join --cutoff 2021-12-31 [--quarters 8] [--synthetic]` | Macro features joined with the PIT panel into `var/data/macro/joined/<id>/` (`joined-synthetic` for the synthetic store) |

Registered series (`multiverse_pipelines/macro/registry.py`): FRED/ALFRED `FEDFUNDS`, `CPIAUCSL`, `UNRATE`, `GDPC1`, `DGS10`, `T10Y2Y`, `USREC`; ECB EUR/USD reference rate, deposit facility rate, euro area AAA 10-year yield; World Bank GDP growth, inflation, unemployment and GDP per capita for the United States and the euro area. Each records geography, frequency, unit, seasonal adjustment, period label, release time zone, publication lag, revision cadence, business days, what the source keeps of earlier publications, and the feature with its transform.

When a value became available (`MacroObservation`):

| Basis | Source | Rule |
|---|---|---|
| `vintage` | ALFRED real-time periods | From the end of the vintage date, US Eastern |
| `snapshot` | World Bank `lastupdated` of each archived response | By the end of that day; an earlier publication is not evidence |
| `schedule` | ECB, values that are never revised | Reference rate 16:00 CET that day; yield curve 12:00 CET next TARGET day; key rates from the start of their day |
| `estimated` | none | Never usable as a feature |

The join (`MacroCell`) gives one cell per company quarter of a PIT panel and per series, over the company's own fiscal quarter (calendar quarter when unknown), made only of observations available at the cutoff, from one vintage. Its reasons are built from the series' rules, never from later publications. States: `observed`, `not_yet_released`, `unavailable` (no key, no decision, nothing downloaded), `not_covered`, `unusable` (first publication not evidenced at the cutoff).

Transforms: `quarter_mean` (all months of the quarter), `quarter_max` (recession), `end_of_period` (last daily value within 10 days of the quarter end), `yoy_last_month`, `yoy_quarter` (one vintage), `latest_year` (latest year available at the cutoff, never after the quarter).

Joined folder: `joined.csv` (financial and macro rows with value, mask, state, availability, synthetic flag, provenance), `macro_cells.jsonl` (every input observation), `manifest.json`; the id `join-<date>-<12 hex>` is the SHA-256 of the PIT snapshot and the macro cells.

## Gate B: dataset audit

`uv run python -m multiverse_pipelines.audit run [--universe data/universe/sec-1000-20261030.json] [--cutoff 2026-10-28] [--leakage-cutoff DATE ...] [--leakage-companies 40]` reads the PIT warehouse, the raw archive, the macro stores and `data/reconciliation/stage-14-manual.json`, and writes `var/data/gate/` (never committed). With a universe the leakage proof rebuilds a seeded sample of 40 companies (the catalog candidates among them), and the report groups companies by SIC division. Exit code 0 when the gate passes, 3 when it is blocked (the report is written either way), 2 when it cannot run.

| File | Content |
|---|---|
| `manifest.json` | `GateManifest`: company decisions, example counts, every check with measures and findings, verdict, SHA-256 of the examples table (`gate-b-<date>-<12 hex>`) |
| `examples.csv` | Every trainable example: company, origin, history, horizon, target quarter, target revenue |
| `data-card.md` | Composition, usable size, coverage, checks, biases, intended use, sources |
| `coverage.html` | Metrics present per company and year, coverage by metric, examples by history and horizon, sectors, currency and standard, checks |

An example is a company and a forecast origin (calendar quarter end) whose last H quarters of revenue (lags 1 to H) were public at the origin, with the revenue h quarters later as first released by the data cutoff. Counts for H = 8, 12, 20 and h = 1, 4, 8, 12, 20.

Checks: future revisions, duplicated company-quarters, concept drift, survivor-only sample, lost bankruptcies (8-K item 1.03), missingness, revenue gaps, negative and undefined ratios, currency and FX, outliers (robust z of log changes), unrealistic quarter-to-quarter jumps, cumulative cash flow, misidentified capex, reported vs calculated EBITDA, source conflicts; then the gate's own: leakage proof (rebuild from what was public at three cutoffs and compare snapshots and macro joins byte for byte), manual reconciliation (10 amounts read from sec.gov, re-checked on every run), usable sample size (at least 30 companies and 1 000 examples at H = 12, h = 4), macro data. Statuses: `pass`, `warning`, `fail`, `blocked`; the verdict is `blocked` exactly when a check fails or is blocked.
