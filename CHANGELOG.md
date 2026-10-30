# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Версии продукта — V0…V4 из `docs/product/04-scope-matrix.md`.

## [Unreleased]

### Changed — 2026-10-30 (data acquisition 14b accepted)

- The data acquisition 14b (decisions D-10, D-11, D-12; universe of 1000 companies; Gate B passed with warnings) accepted by the owner (CI run 41129053273 green).

### Added — 2026-10-30 (data acquisition: decisions D-10, D-11, D-12)

- Owner decisions recorded in the source catalog: D-10 (SEC bulk files `companyfacts.zip` and `submissions.zip`, a universe of 1000 companies, 10 GB on disk), D-11 (FRED/ALFRED, 7 series), D-12 (ECB, 3 series; World Bank, 4 indicators for the United States and the euro area). Financial Statement Data Sets stay undecided.
- Real macro store: all 18 registered series (FRED 41 779, ECB 22 953, World Bank 463 observation intervals). Daily H.15 rates (DGS10, T10Y2Y) are read as current values, public by the end of the second weekday after their day: ALFRED caps a request at 2000 vintage dates and these series are not revised.
- Study universe (`python -m multiverse_pipelines.sec universe`, ADR-0022): 1000 companies drawn from the archived bulk files by written rules and seed 20261030, stratified by SIC division, the ten catalog candidates always included; 20 529 companies with Company Facts → 10 152 with 12+ XBRL 10-K/10-Q → 8 185 outside the excluded financial sectors → 7 573 with a revenue concept. 347 of the 1000 have deregistered. Manifest `data/universe/sec-1000-20261030.json`; 2 345 files (1 751 MB) copied out of the ZIPs into the raw archive byte for byte, addressed `<zip url>#<member>`.
- Contracts 0.12.0: `UniverseManifest`, `UniverseCompany`, `UniverseStratum`, `RuleCount`, `BulkFile`.
- PIT warehouse at scale: payloads zlib-compressed with a dictionary stored in the file (about 7× smaller), companies built in parallel and streamed into the file one at a time, filings cached; `pit build --universe` built 1000 companies (3.86 million value intervals, 1.3 GB) in 14 minutes.
- Gate B at scale: `audit run --universe`, slim records for the checks, one panel instead of two, the leakage proof on a seeded sample of 40 companies with the candidates, the macro check over the real store, survivorship measured on the universe, the report grouped by SIC division.
- Macro join with real data at 2025-12-31 for the universe (`join-20251231-b88170136556`): 144 000 cells, 74 983 observed, 65 062 unusable (World Bank snapshot; FRED marks October 2025 missing for unemployment and CPI), 3 955 not yet released.
- Gate B on the universe (`gate-b-20261028-419fc004fe0e`): **passed with warnings**: 899 companies with 12+ revenue quarters and 17 508 examples at H = 12, h = 4; leakage proof identical at three cutoffs; reconciliation 10 of 10; 14 warnings on properties of the real data (survivorship after 12 XBRL reports, missingness, concept drift, outliers, macro coverage).
- Tests never reach the network (`pipelines/tests/conftest.py`).

### Fixed — 2026-10-30 (data acquisition)

- A company with no filings at a cutoff showed attribute reasons that depended on its later first filing; before its first filing every attribute is now empty with one reason (leakage proof).
- Former names listed for one day (from = to) broke the attribute contract; such a name holds that day.
- A fiscal year label more than a year from its period end (a 10-K that tags fiscal 2015 as 1215) is ignored; the year is named by its end.
- US daylight saving rules for 1967–1986 (old ALFRED vintages); World Bank disappearance scoped to one indicator; FRED error messages never print the key.
- Cumulative cash flow: Q4 equal to the year after three zero quarters is arithmetic, not an error. Source conflicts: estimates (a period ending after its filing) are already left out of every view, so they are a warning with the cases; any other blocking alert still fails.
- The Data Catalog download badge wraps on a 390 px card.
- `sec verify` lists unknown archive files in a stable order (directory order differs between file systems; CI on Linux failed on it).

### Changed — 2026-10-30 (Stage 14 accepted)

- Stage 14 (Gate B dataset audit) accepted by the owner (CI run 41043307647 green). The gate verdict stays blocked until decisions D-10 (SEC bulk files), D-11 (FRED key) and D-12 (ECB, World Bank).

### Added — 2026-10-30 (Stage 14)

- Gate B dataset audit (`python -m multiverse_pipelines.audit run`, ADR-0021): the 15 checks of the prompt (future revisions, duplicated company-quarters, concept drift, survivor-only sample, lost bankruptcies, missingness, revenue gaps, negative and undefined ratios, currency, outliers, unrealistic jumps, cumulative cash flow, misidentified capex, reported vs calculated EBITDA, source conflicts) plus a leakage proof, manual reconciliation, usable sample size and macro data; statuses pass, warning, fail and blocked.
- Usable examples instead of file counts: a company and forecast origin with H quarters of public revenue history and the revenue h quarters later as first released, for H = 8, 12, 20 and h = 1, 4, 8, 12, 20; the examples table names the dataset by its SHA-256.
- Data card and coverage report (company × year heat map, coverage by metric, examples by history and horizon, sectors, currency and reporting standard, checks) and per-metric inclusion decisions.
- Ten manual reconciliations of derived amounts (Q4 = fiscal year − nine months) with the original filings on sec.gov for Stryker, Old Dominion, Waste Management, Akamai and Celgene, stored in `data/reconciliation/stage-14-manual.json` and re-checked on every run: 10 of 10 match.
- Contracts 0.11.0: `GateCheck`, `ExampleCount`, `CompanyDecision`, `GateManifest`.
- Verdict on the SEC sample: **blocked** (10 companies, 447 examples at H = 12 and h = 4 against the proposed 30 companies and 1 000 examples; no real macro data). Leakage proof and reconciliation pass.

### Changed — 2026-10-30 (Stage 13 accepted)

- Stage 13 (macro vintages) accepted by the owner (CI run 41036165376 green). Real macro downloads still wait for decisions D-11 (FRED key) and D-12 (ECB, World Bank).

### Added — 2026-10-30 (Stage 13)

- Macro vintages (`python -m multiverse_pipelines.macro`, ADR-0020): a registry of 18 series (FRED/ALFRED policy rate, CPI, unemployment, real GDP, 10-year yield, 10y–2y spread, recession indicator; ECB EUR/USD reference rate, deposit facility rate, euro area AAA 10-year yield; World Bank GDP growth, inflation, unemployment and GDP per capita for the United States and the euro area) with geography, frequency, unit, seasonal adjustment, period label, release time zone, publication lag, revision cadence, business days and the chosen transform.
- Every observation carries when it became available and how that is known: ALFRED vintages (end of the vintage date, US Eastern), dated World Bank snapshots, ECB publication rules for unrevised values (16:00 CET, next TARGET day 12:00 CET with TARGET holidays); estimated releases are never usable.
- A vintage store (SQLite) and the as-of join with company quarters of the PIT panel: one cell per company quarter and series over the company's own fiscal quarter, made only of observations available at the cutoff from one vintage, with provenance; states observed, not yet released, unavailable, not covered, unusable. Reasons never mention later publications.
- Downloads behind the same locks as SEC plus the FRED key; the key is never stored (archived URLs show `api_key=REDACTED`), FRED series whose notes mention copyright are skipped. Without a key or decision the commands report what is missing and the join says why in each cell.
- SYNTHETIC documents in the shape of ALFRED, ECB and World Bank responses, kept in a separate store and folder, so the whole path runs before decisions D-11 and D-12.
- Series coverage and timestamp QA (publication lag, revised periods, values published before their period ended, gaps, missing values) and a joined sample panel with provenance.
- Contracts 0.10.0: `MacroSeries`, `MacroObservation`, `MacroCell`.

### Changed — 2026-10-30 (Stage 12 accepted)

- Stage 12 (point-in-time warehouse) accepted by the owner (CI run 40981425041 green).

### Added — 2026-10-30 (Stage 12)

- Point-in-time warehouse (`python -m multiverse_pipelines.pit`, ADR-0019): every normalized value with the interval of knowledge time during which it was the current answer, in one SQLite file (`var/data/pit/`, never committed). The Stage 11 normalizer runs again at each moment a filing became public, on exactly the facts public then, so an as-of query equals normalizing what was public at the cutoff.
- EDGAR's clock: a filing is public from its acceptance time (UTC in the submissions file, checked on the sample), never before the start of its filing date in US Eastern time; a date cutoff is the end of that day. A cutoff of 31 December never sees a filing dated in January.
- Knowledge views `vintage` (default for features), `original` (first release) and `latest` (hindsight, refused by panels and snapshots); `as-of`, `history` (corrections of one period over time) and `entity` commands.
- Complete quarterly panel by calendar quarter with feature masks and a reason for every empty cell (not yet filed, not reported, blocked, inactive after a Form 15, not covered); trailing-twelve-month and growth features computed from panel cells only.
- Reproducible snapshots named by the SHA-256 of their canonical content, with panel, features, lineage export (source facts, filing URLs, raw file checksums) and manifest; `leakage-check` rebuilds from only what was public at a cutoff and compares the hash.
- Chronology alerts (estimates inside filings, filing date mismatches, late acceptances, filings missing from the index, amendments before originals, reports out of order, late reports, deregistrations, quarters that do not add up to the year) and a coverage dashboard (HTML, Markdown, JSON) with explicit firm-quarter counts per metric.
- Names follow their official dates; current tickers, exchanges and SIC codes apply only from when they were observed, never backwards.
- Contracts 0.9.0: `PitValue`, `PanelCell`, `ChronologyAlert`, `PitSnapshotManifest`, `EntityAttribute`.

### Changed — 2026-10-30 (Stage 12)

- XBRL normalization: a latest derived value that combines a revised part with a part filed before that revision is flagged `mixed_vintage` (116 rows of the sample). The fiscal calendar can add a provisional year after the last 10-K; Stage 11 output does not use it.

### Changed — 2026-10-30 (Stage 11 accepted)

- Stage 11 (XBRL normalization) accepted by the owner (CI run 40956130754 green).

### Added — 2026-10-29 (Stage 11)

- XBRL normalization (`python -m multiverse_pipelines.xbrl normalize | show`, ADR-0018): canonical values of 14 metrics (revenue, COGS, operating income, net income, R&D, D&A, CFO, capex, cash, three debt measures, diluted shares, shares outstanding) plus free cash flow and EBITDA (not adjusted) with their formula.
- Concept map with relations (primary, equivalent, narrower, broader); one concept per company and fiscal year; other candidates kept as reconciliation evidence, with a flag when equivalents disagree.
- Fiscal calendar from each company's 10-K periods (52/53-week years, year labels from the filing); quarters as reported, from year-to-date differences, or Q4 as fiscal year minus nine months or three quarters, never mixing concepts. Averages and instant values are never derived.
- Two revisions per value (as first filed, as last filed) with restatement and amendment flags; checks for units, currencies, scale, rounding, negative expenses, duplicates and conflicting values in one filing.
- Contracts 0.8.0: `NormalizedValue` with source facts and signs, method, knowledge date, quality and flags; the value must equal the signed sum of its sources, and missing is never zero. `LineageMethod` gains `fy_minus_three_quarters`.
- Standardized tables in `var/data/normalized/sec/` (JSONL, CSV, schema, coverage data card, manifest with input checksums).
- 40 new tests; manual reconciliation of Texas Instruments, Union Pacific and AMETEK for fiscal 2025 against the original filings: 75 of 75 values match.

### Changed — 2026-10-29 (Stage 10 accepted)

- Stage 10 (SEC raw ingestion) accepted by the owner (CI run 40951293218 green).

### Added — 2026-10-29 (Stage 10)

- SEC raw ingestion (`python -m multiverse_pipelines.sec`, ADR-0017): connectors for the Submissions API (with the older-filing pages it lists), the Company Facts API and bulk ZIPs (`companyfacts.zip`, `submissions.zip`, quarterly Financial Statement Data Sets). Commands `status`, `sample`, `probe`, `bulk`, `verify`, `coverage`.
- Three locks before any download: `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true` for one command, a User-Agent with a name and contact email, and the owner's approval in the source catalog; bulk files need a bulk approval.
- HTTP client: official hosts over HTTPS only (redirects included), one throttle at 2 requests per second, retries for 429, 5xx, cut connections and short bodies with exponential backoff or Retry-After, stop on 403, size limit from the disk budget.
- Immutable raw archive in `var/raw/sec/`: read-only files named by SHA-256, append-only metadata index, an audit manifest per run, freshness and stale-response rules, recovery after interruption, `verify`. JSON and ZIP files are checked before they are kept.
- Settings `MULTIVERSE_RAW_DIR` and `MULTIVERSE_RAW_BUDGET_MB` (200).
- Contracts 0.7.0: the scope of an owner's download approval (sample or bulk) and the date of an acquisition step's decision.
- 74 new tests on synthetic fixtures through a fake SEC; the real network is blocked in tests.

### Changed — 2026-10-29 (Stage 10)

- Decision D-09: the owner approved an SEC sample (ten candidates, submissions and company facts, one HEAD request for `companyfacts.zip`, 200 MB budget). The catalog records it; bulk files still wait for decision D-10.
- Data Catalog: the SEC badge says "sample only", the plan marks step 1 as decided, and the texts say the app shows no source data.
- Sample downloaded locally: 34 requests, 34 files, 37.5 MiB; raw files are not committed.

### Changed — 2026-10-29 (Stage 09 accepted)

- Stage 09 (source policy and Data Catalog) accepted by the owner (CI run 40916903384 green). Metadata only: no data downloaded; automatic downloads stay disabled until decisions D-09 to D-12.
- Overview: the build progress shows phase B as in progress, with no data yet; the status line can wrap on narrow screens.

### Added — 2026-10-29 (Stage 09)

- Contracts 0.6.0: `SourceCatalog` with sources, datasets and data dictionaries, licences with separate redistribution and resale status, key status, documented and chosen request rates, retry and checksum rules, download decisions, risk register, sector priorities, scoring rubric, company candidates and the acquisition plan (ADR-0016).
- Source catalog generated by `python -m multiverse_contracts.source_catalog`: SEC EDGAR, FRED/ALFRED, ECB Data Portal and World Bank, with documentation checked on 2026-10-29; licensed market data listed as needs without a provider. Metadata only; automatic downloads stay disabled and every source awaits the owner's decision.
- Data Catalog (`/data-catalog`): search over sources, datasets, identifiers, formats and fields, with or without JavaScript; access filter; a page per source with access, licence, limits, retries, checksums, documentation and data dictionary; the acquisition plan with the risk register, sectors, rubric and the first ten companies.
- Tables can wrap long text in a column instead of widening.
- Tests: 23 pytest, 14 vitest and Playwright checks for search, filters, the SEC contract, the plan, 404 and accessibility.

### Changed — 2026-10-29 (Stage 08 accepted)

- Stage 08 (Gate A) accepted by the owner (CI run 40904304678 green). V1 Interactive prototype is complete; no tag or GitHub release.
- Overview: the build progress shows phase A as done on synthetic data.

### Added — 2026-10-29 (Stage 08, Gate A)

- Gate A frontend audit: 20 formal test cases with actual results; all P0 pass (`docs/stages/08-frontend-test-gate.md`).
- `e2e/gate-a.spec.ts`: every route at 1440, 768 and 390 px (status, console errors, overflow, one heading, demo labels, copy audit, axe WCAG 2.2), internal links, the whole journey from search to exported report, keyboard only, focus rings, reduced motion, refresh, unit conversion and data consistency.
- `e2e/performance.spec.ts`: load and interaction observations on request (`OBSERVE_PERF=1`).
- Release note for V1 Interactive prototype (`docs/releases/v1-interactive-prototype.md`); no tag or GitHub release.
- Tests: 160 Playwright checks.

### Fixed — 2026-10-29 (Stage 08)

- Universe Explorer: a result clicked within 300 ms of typing was replaced by the pending search.
- Overview: the disabled "Launch a scenario" button and its "arrives in Stage 05" note are replaced by a link to the Decision Builder; the build progress no longer says Stage 03.
- Settings & Privacy no longer promises display settings with Gate A and no longer says it deletes display settings that do not exist.
- Design system example badge no longer names a finished stage.

### Changed — 2026-10-29

- Stage 07 accepted by the owner (CI run 40848057488 green).

### Added — 2026-10-29 (Stage 07)

- Contracts 0.5.0: `ScenarioRecord` with append-only revisions, `ReportSnapshot` with a SHA-256 of its content and a manifest, and the `NotebookExport` file with a schema version (ADR-0015).
- Research Notebook (`/notebook`), stored only in this browser and labelled so: search by name, tag, notes or company; tag filter; editable name, tags and notes; revision history; open a revision in the Decision Builder; duplicate as a new scenario; compare two revisions, blocked for different cutoffs, horizons or currencies; Markdown reports with the reproducibility manifest that never change after export.
- Decision Builder: Save to notebook as a new scenario or as the next revision of a restored one.
- Import and export of the notebook as JSON: whole-file validation, refusal of newer versions and changed reports, migration of decision files from Stage 05, merging without overwriting.
- Storage failures handled: private mode, full storage and unreadable data, which is never overwritten without a decision.
- Settings & Privacy (`/settings`): what is stored on this device, and delete everything after confirmation.
- Tests: 19 pytest, 28 vitest and 48 Playwright checks.

### Fixed — 2026-10-29

- The Run dialog form was nested inside the Decision Builder form since Stage 05: invalid HTML, a hydration error, and dialog buttons that submitted the outer form. The actions now sit after the form.

### Changed — 2026-10-28

- Stage 06 accepted by the owner (CI run 40756212363 green).

### Added — 2026-10-28 (Stage 06)

- Contracts 0.4.0: `ScenarioResult` with reported history, p10/p50/p90 paths per scenario, paired changes computed path by path, change distributions, waterfalls on means, decision events, a manifest and a failed state (ADR-0014).
- Mock result generator `python -m multiverse_contracts.mock_results`: deterministic paired paths on the synthetic dossiers, labelled demo and mock; one failed run.
- Timeline Explorer (`/timeline`): SVG timeline with history and forecast, bands, decision marker, legend toggles, crosshair tooltip with units and sources, keyboard reading, absolute / change / percent, KPI cards, table view, CSV export with a synthetic warning, event timeline.
- Universe Compare (`/compare`): side-by-side KPIs, waterfalls, distributions of paired differences, and a cross-result comparison that blocks different cutoffs, currencies or horizons.
- Chart series tokens validated with the dataviz palette validator; honest axes that include zero.
- Tests: 18 pytest, 24 vitest and 81 Playwright checks for chart and KPI consistency, paired changes, axes, rounding, CSV, compatibility, keyboard, failed and unknown results, accessibility.

### Changed — 2026-10-28

- Launch Center moved to Stage 22 (Monte Carlo engine). The Decision Builder's Run dialog points to the mock results.
- A scenario draft keeps its own contracts version on a JSON round trip.
- Stage 05 accepted by the owner (CI run 40725947738 green).

### Added — 2026-10-28 (Stage 05)

- Contracts 0.3.0: `ScenarioDraft` with six decision types (R&D change, workforce restructuring, acquisition, divestiture, CAPEX expansion, debt refinancing), typed magnitudes with explicit units, timing, fixed / uniform / triangular distributions, financing or use-of-proceeds shares and sensitivity settings.
- Intervention catalog generated by `python -m multiverse_contracts.catalog`: units, allowed and planning ranges, defaults with their source, mechanism and evidence level per decision type (ADR-0013).
- Rule codes shared by the Python and web validators, checked on the same fixtures in pytest and vitest.
- Exact decimal arithmetic in the web app for shares, unit conversion and amounts.
- Decision Builder (`/decisions`): reusable number, slider, distribution and share inputs; Validate with an error summary; Reset to documented defaults; eligibility by company and cutoff; the decision translated into dollars at the cutoff; results marked stale when the cutoff changes; Run enabled only for a fresh, valid decision.
- Assumption Matrix (`/assumptions`): every parameter with its ranges, default and source.
- Tests: 47 pytest, 63 vitest and Playwright journeys for units, ranges, financing mix, stale results, eligibility, keyboard sliders and accessibility.

### Changed — 2026-10-28

- Stage 04 accepted by the owner (CI run 40713741194 green).

### Added — 2026-10-28 (Stage 04)

- Contracts 0.2.0: company identity with ticker and name histories, filings, coverage, data quality flags, company dossier and value lineage; the JSON Schema is now exported in serialization mode.
- Synthetic demo fixtures: seven fictional companies generated by `python -m multiverse_contracts.demo`, validated by the contracts and checked for drift.
- `CompanyRepository` interface with a fixture implementation, mapped to future `/api/v1` endpoints (ADR-0012).
- Universe Explorer: search by ticker, former ticker, name and CIK; sector, country, lifecycle and coverage filters; works without JavaScript.
- Company Dossier: identity, listing history, quarterly financials with a lineage toggletip per value, as-of cutoff, amount scale, coverage, data quality and filings.
- Safe URL handling: allowlisted parameters, length limits, 404 for unknown companies, external links only to official HTTPS hosts.
- Tests: 24 pytest, 29 vitest and Playwright journeys for search, empty and unsupported states, currency change, cutoff and accessibility.

### Changed — 2026-10-28

- Stage 03 accepted by the owner. Time Machine moved to Stage 12; a single-company cutoff now lives in the Company Dossier.

### Added — 2026-10-28 (Stage 03)

- `apps/web`: Next.js 16 + TypeScript strict + Tailwind CSS 4 web app with the MULTIVERSE design system.
- Design tokens from `docs/10` in `src/tokens/tokens.css`, with WCAG contrast tested from the file itself.
- Components: buttons, text / select / checkbox fields, native modal dialog, responsive data table, alerts, badges, skeleton; trust components for result mode, provenance, result header and "what this does not mean".
- Application shell: skip link, collapsible sidebar, top bar with breadcrumbs, swipeable navigation drawer below 1024px, footer; 20 sections, 18 of them honest placeholders that name their stage.
- Pages: Overview with the diverging-timelines hero, Methodology, Design system, 404.
- Tests: vitest (tokens, navigation) and Playwright at 1440, 768 and 390 px (overflow, axe WCAG 2.2, keyboard, dialog, drawer, motion, table, links); new `web` CI job.

### Changed — 2026-10-28

- Stage 02 accepted by the owner.

### Added — 2026-10-28 (Stage 02)

- Monorepo: uv workspace (8 Python packages, Python 3.12) and npm workspace (`@multiverse/contracts`), one command surface in `package.json`.
- Contracts as a single source of truth: Pydantic models → `contracts.schema.json` → generated TypeScript types, with drift checks (ADR-0008).
- Validated settings with `local / test / ci / production` profiles and safe defaults (ADR-0010).
- API composition root with `GET /api/v1/health`; worker composition root.
- Module boundaries enforced by import-linter and ESLint (ADR-0009).
- Quality gate `npm run check`, GitHub Actions CI (Ubuntu and Windows), secret scan test, gitleaks in CI.
- ADR-0001…0011, engineering conventions, root README with Windows / Linux quick start.

### Changed — 2026-10-28

- Stage 00 and Stage 01 accepted by the owner, including the defaults of all open questions.

### Added — 2026-10-28 (Stages 00–01)

- Stage 00: подтверждение мастер-промпта и реестр 14 научных рисков (`docs/stages/00-orchestrator-briefing.md`).
- Stage 01: продуктовые требования (`docs/product/`): PRD, personas, user stories и failure cases, scope matrix V0–V4, product risks, open questions с defaults, словарь финансовых величин, acceptance checklist.

### Notes

- Stages 00–01 contained documents only. Stage 02 adds infrastructure code; there is still no dataset, model or business logic. All acceptance matrix items remain TODO.
