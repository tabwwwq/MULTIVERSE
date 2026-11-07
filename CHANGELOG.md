# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Версии продукта — V0…V4 из `docs/product/04-scope-matrix.md`.

## [Unreleased]

## [v2.0.0-research] — 2026-11-07

Research preview, local only: the git tag the owner approved on 2026-11-07. Release note: `docs/releases/v2-research-preview.md`. It holds everything below down to Stage 15; the empirical tier is not met, and no site is deployed.

### Added — 2026-11-07 (Stage 26, final review)

- Acceptance audit against docs/17 with the evidence of each requirement: 25 of 31 met, 5 partial, 1 blocked. The six gaps (live screen reader, user study, second human reviewer of events, placebo diagnostics, cold rebuild from raw data, Safari and Firefox on phones) are in the issue register, now 42 entries.
- Release criteria for the demo, research and empirical tiers: the empirical tier is not met, so no release presents forecasts or scenarios as validated; a public deployment may show the demo tier only until TLS and a browser login exist.
- Maintenance runbook (start, monitoring hooks, backup before upgrades, upgrade and rollback, data and model refresh with measured times, incidents), `SUPPORT.md`, a source card and a draft release note for v2.0.0-research. Nothing was published.
- `npm run smoke`; Playwright runs in another time zone with `E2E_TZ`. A fresh clone of the public repository reached green smoke tests in 148 s; the desktop browser suite passed in UTC+14 and in Los Angeles.

### Changed — 2026-11-07 (Stage 25 accepted)

- Stage 25 (Report Studio, case studies, portfolio; CI run 42392124203 green) accepted by the owner.

### Added — 2026-11-07 (Stage 25)

- **Report Studio** (ADR-0034): the research report of a finished run in ten sections, with every number a claim that points into the run and every claim citing its sources; Markdown, CSV, the document as JSON, print to PDF from `/reports`, and a manifest. `python -m multiverse_simulation replay` builds a report again and compares it byte for byte; a real report of Intel replayed identically in 63 s.
- The worker writes the report after each run (`multiverse-worker reports` for earlier runs); the API serves its files to the owner of the run only.
- Three case studies in `docs/case-studies`: R&D allocation (Intel), M&A stress (Boeing), restructuring or exit (Estée Lauder), each with two runs, figures, a comparison and what it does not show. All 12 SEC filings they cite resolved.
- `docs/portfolio`: the write-up with measured results and failures, interview questions, resume bullets flagged after implemented, a demo script and six screenshots; the README shows screenshots below the limitations.
- Contracts 0.23.0: `ResearchReport`, `ReportManifest`, `ReplayCheck`.

### Changed — 2026-11-07 (Stages 24 and 24b accepted)

- Stage 24 (security, privacy, licences; CI run 42270739506 green) and Stage 24b (real companies; CI run 42377104890 green) accepted by the owner. The FRED licence blocks stay open, and the model without FRED stays research only.

### Added — 2026-11-07 (Stage 24b, decision D-14)

- **Real companies on the screens** (ADR-0033): the 500 largest SEC filers by the public float on the cover of their 10-K, NVIDIA first. The rank is labelled as not market capitalization; companies without a 10-K (Saudi Aramco, Samsung, TSMC) are not there. The seven fictional companies follow them, labelled.
- **A forecast for 496 of them** from a temporal network trained without FRED: SEC filings of 1,429 companies, U.S. Treasury yields read from the Treasury, ECB rates. On the test years 2020 to 2026 it beats persistence by MAE on revenue growth at 4 quarters by 31.7% (33.4 to 29.9%) and the best baseline by 4.7%; at 1 quarter it is 11.8% worse than gradient boosting. Its p10 to p90 ranges held 82.2% of outcomes for revenue growth over 4 quarters on 2024 to 2026 (80% stated); under the approval rule of Stage 17, 2 of 15 target and horizon pairs pass (revenue growth over 4 and 8 quarters). Research only, not approved for the product.
- **Run works**: the Decision Builder sends a real company's case through the queue, the worker computes paired Monte Carlo paths and `/run?job=` shows the report. 373 companies have a case; 88 of them stand on a substitute for EBITDA (operating income plus D&A, or cash from operations), and the dialog says so before the run. Banks, insurers and REITs have none.
- `npm run app` starts the API, the worker and the site (or only the first two when the site already runs).
- `sec top`, `multiverse_forecast live` and `multiverse_simulation companies` (which replaces `case`); the U.S. Treasury as a source; contracts 0.22.0.

### Fixed — 2026-11-07 (Stage 24b)

- Filing fee tables (`ffd`) no longer enter the warehouse: JPMorgan alone filed 4,260, and each one recomputed its whole history. The build of 1,429 companies took 23.5 minutes.
- Fiscal years before 1990 are left out of the calendar: a filer had typed 1989.
- The forecast no longer feeds a feature to the model that no training row had (World Bank series have no dated vintages).

### Security — 2026-11-06 (Stage 24)

- The API checks who is asking (ADR-0032): `local` mode serves the loopback only, `token` mode needs a Bearer token with a role and an expiry. Settings refuse `local` in production and off the loopback.
- A guard outside the app refuses a foreign `Host`, cross-site writes, bodies that are not JSON and bodies above 256 KB. Before this stage a page of any site could create and approve a job on the local API.
- A job belongs to whoever submits it. Someone else's job answers 404, idempotency keys are per owner, and only an admin approves an estimate, under the name of the token.
- Limits live in the queue: the cloud spending limit is enforced for the first time, at submit, approval and when a worker takes a job, with limits on active jobs and on compute per day.
- Every protected read and action is in an audit log with no address and no token, kept 90 days. `GET /me/export` and `POST /me/erase` serve GDPR access and erasure.
- `protocol_path` takes only protocols of this repository. CSV cells cannot run as formulas, Markdown reports escape markup, pages carry a Content-Security-Policy and other headers.
- `multiverse-worker backup`, `verify` and `restore`, tried on the real queue.
- CI actions are pinned to full SHAs, a new job audits dependencies, ruff runs its security rules, setuptools moved to 84.2.1.
- `docs/security/`: threat model, a register of 36 issues, licence inventory, GDPR data inventory, privacy policy outline, runbooks. `docs/governance/`: model and data cards.

### Found — 2026-11-06 (Stage 24)

- **The FRED terms forbid machine learning on FRED content and archiving it through the API.** Stages 15 to 17 trained on seven FRED features, and the archive holds the series. New training on them is refused and the blocks are shown in the Data Catalog; nothing was deleted or retrained. The owner decides (OQ-21).

### Changed — 2026-11-06 (Stage 23 accepted)

- Stage 23 (valuation and risk studio) accepted by the owner (CI run 42242972932 green). Its values stay model values, not verified market values.

### Added — 2026-11-06 (Stage 23)

- Valuation Studio (`/valuation`, ADR-0031): editable WACC parts, terminal growth or exit multiple, horizon, projected FCFF, tax, bridge and dilution; enterprise value and equity value as separate outputs with a bridge; DCF by quarter and year; both terminal methods compared; a WACC × g matrix where WACC at or below g has no value; a tornado through the full statements; a method panel and CSV files.
- Risk Observatory (`/risk`): credit and liquidity shares of paths under the assumed model, bear, base and bull runs on the same shocks with editable weights, eight stress cases, an adverse story told from the numbers of the path, the worst paths.
- `ValuationReport` (contracts 0.20.0, `python -m multiverse_simulation studio`) with a manifest and ten quality checks. Seven are required: a report that fails one cannot exist. Every report carries the label "Model value, not a verified market value".
- Finance 0.4.0: exit multiple, implied growth, the sensitivity matrix, scenario weights, retained share, maturity wall.
- The browser repeats only the discounting, on statements the engine reconciled, and a test holds it to the Python report on every cell. OQ-12 closed: no price per share in V1 to V3.

### Changed — 2026-11-06 (Stage 22 accepted)

- Stage 22 (paired Monte Carlo) accepted by the owner (CI run 42228195449 green). Its probabilities stay conditional on the assumed model, not validated.

### Added — 2026-11-06 (Stage 22)

- Paired Monte Carlo `multiverse_simulation` (ADR-0030): on every path the baseline and the alternate share one draw of exogenous shocks; only the decision and its own parameters differ. Every path goes through the finance engine, so identities hold path by path.
- Shocks are whole rows of history: macro, sector and firm columns of one calendar quarter, drawn by a stationary block bootstrap, so links between columns and over time survive without a covariance model.
- One seed per path: a decision never moves a shock, and batch size, stop and resume never change a number. Impossible draws are redrawn and counted; a path that does not reconcile stops the run.
- Report with quantiles, paired changes, risks with Monte Carlo error and a Wilson bound, convergence at 500, 1000, 3000 and 10 000 paths, the ten worst paths, sensitivity to the shock model and a reproducibility manifest. Contracts 0.19.0 refuse a report that claims calibration: probabilities are labelled conditional on the assumed model, not validated.
- A research case on real data (`data/simulation`): Hubbell Inc at 2025-12-31, each input marked observed, implied, assumed or from the model, with an invented acquisition. Over 10 000 paths the covenant breach probability is 18.1% against none seen in the baseline; a choice of block length moves it more than Monte Carlo error does.
- Every run goes through the queue: `POST /api/v1/simulations`, an approved estimate, a worker, budgets and stops at a batch of paths. A job now has a `kind`; rows stored earlier read as trainings.
- Launch Center (`/launch`): the warning first, readiness, paths, paired change, risks, worst paths, convergence, sensitivity, diagnostics and a way to start a run. Charts and CSV of a real run no longer say mock.
- Finance 0.3.0: a rate shift per quarter, a chosen value for each uncertain parameter, a target that can follow the company.

### Changed — 2026-11-06 (Stage 21 accepted)

- Stage 21 (financial engine) accepted by the owner (CI run 42213997840 green). Its numbers are synthetic so far.

### Added — 2026-11-06 (Stage 21)

- Financial engine `multiverse_finance` 0.2.0 (ADR-0029), independent of the UI and of neural frameworks: a baseline and decisions become three linked statements, and `project` refuses a path that does not reconcile to the cent.
- Event accounting of the six decisions as ledger entries: R&D now and revenue later, severance and payroll, acquisition with funding mix, purchase allocation and late synergies, divestiture with stranded overhead, CAPEX with construction and utilization, refinancing. A decision of the contract reaches the engine through `plan_for`.
- CFO − CAPEX, FCFF and FCFE kept apart with an exact bridge in every quarter; WACC, a quarterly DCF whose value does not depend on the horizon, and the bridge from EV to equity value. `enterprise_value` reads a path, so only FCFF can meet WACC.
- Negative cash cannot appear: a deficit above the revolver limit becomes a named funding shortfall. Bad inputs are refused with a code; a sound input without a meaningful answer is undefined and says why.
- Stress cases: revenue −20%, margin compression, rates +200 bps, closed refinancing, working capital absorption, covenant threshold.
- Finance whitepaper (`docs/finance/financial-engine-whitepaper.md`) with journals, US GAAP and IFRS limits, EBITDA adjustments and a synthetic worked example checked by a test.
- Property tests with hypothesis (new dev dependency) and a fourth import-linter contract: finance knows no neural framework. Contracts unchanged (0.18.0).

### Changed — 2026-11-06 (Stage 20 accepted)

- Stage 20 (causal feasibility study) accepted by the owner (CI run 42136489532 green). No effect is estimated; the gate of the event registry audit stays closed.

### Added — 2026-11-06 (Stage 20)

- Causal feasibility study (ADR-0028), labelled as such: no effect is estimated, and no outcome after a treatment is read. The contract has no field for an effect, and the estimator refuses to run until the audit of the event registry says the sample is credible.
- The causal graph with unobserved management expectations, rationale for every edge, what it leaves out, and an estimand, assumptions and untestable assumptions for each of the six decisions.
- Blind diagnostics (`python -m multiverse_causal study`): propensity support, balance, pre-trends, placebo dates, a null from pseudo-events on firms without the action, the smallest detectable effect, E-values and the pre-period fit of synthetic controls. A test replaces every treated value after the event and no number changes.
- Study `cst-20261106-b225726a46d3`: 0 of 24 method and decision pairs are feasible. 29 of 48 events are usable. With today's events only a shift of 0.5 to 1.1 in symmetric growth could be seen; with every candidate read, about 0.03 to 0.08.
- Causal Map (`/causal-map`): the warning first, the graph drawn and in words, feasibility by decision, and why each method is closed.
- `events index`: the 8-K decision items of the universe for the causal package. Contracts 0.18.0: `CausalGraph`, `TreatmentStudy`, `CausalStudy`.

### Changed — 2026-11-06 (Stage 19 accepted)

- Stage 19 (event registry) accepted by the owner (CI run 42131812836 green). Causal work stays blocked by its audit.

### Added — 2026-11-06 (Stage 19)

- Corporate event registry (ADR-0027): a taxonomy of six decisions, annotation guidelines, and a first hand-read sample. An event exists only after its primary document was read; the announced intention and the executed treatment are separate fields, and every value is read in a named place or listed as unknown.
- Decision D-13 (owner in chat): up to 150 filing documents within 200 MB. 60 documents (38 MB) fetched behind the three download locks into the immutable archive.
- Sample `evs-20261106-3cc4abd6372b` (`python -m multiverse_pipelines.events sample`): five strata from the archived filing index and the Stage 15 dataset, one filing per firm, a third from companies that later left EDGAR reporting, seed 20261106.
- Registry `data/events/registry.json`: 60 filings read, 48 events and 12 rejections kept with their reason (SPAC mergers, new debt that replaces nothing, intensity moved by revenue, one error of the filing index). Reviewed by one AI reviewer only, said so on every event.
- Audit (`events audit`): composition, unknown fields, reviews, overlap inside the registry and against unread 8-K filings. Verdict: not credible, causal work blocked: no type reaches 30 events and no event has a human review. All 8 layoffs have debt filings in their window, and the documents themselves name something else going on for 22 of 48 events.
- Event Registry (`/events`, `/events/[eventId]`): the block, filters, intention next to execution, unknowns, what happened at the same time, the link to the filing, and a review form; reviews stay in the browser until downloaded and merged with `events reviews --file`.
- Contracts 0.17.0: `CorporateEvent`, `EventEvidence`, `EventReview`, `EventMagnitude`, `EventFunding`, `EventCandidate`, `CandidateSample`, `EventRegistry`, `QualityAudit`.

### Changed — 2026-11-06 (Stages 16, 17 and 18 accepted)

- Stages 16, 17 and 18 accepted by the owner (CI runs 42106520404, 42120259862 and 42124978629 green). Model `model-20261028-9ce4d4180aa9` is signed for research on three target and horizon pairs only; nothing in the product uses it.

### Added — 2026-11-05 (Stage 18)

- Training jobs outside any HTTP request (ADR-0026): a durable SQLite queue (`multiverse_jobs`), workers with leases and heartbeats, a real checkpoint, stop, pause and resume, budgets, retries and alerts.
- A job starts only after its estimate of time, GPU memory, disk and cost is approved; the same idempotency key returns the same job, and another request with it is refused.
- Checkpoints (`multiverse_forecast.resumable`) hold model, optimizer, scheduler, every random state, counters and normalization; `last.pt` after each epoch and `best.pt` on improvement, written atomically with their SHA-256; resume refuses another dataset, fold, feature schema, normalization or architecture.
- Worker (`multiverse-worker run | status | kill`): exits when the queue is empty, so nothing trains overnight by accident; a loss that is not a number alerts and fails, running out of device memory retries with half the batch, other errors retry from the checkpoint until the attempts end. Budgets of time and money count all attempts together and are checked at safe points; more than four hours needs `overnight: true`.
- API `/api/v1/jobs`: estimate, submit, list, detail, logs, approve, pause, stop, resume. Logs are stripped of keys, tokens, addresses and long hashes before they are stored.
- Model Observatory (`/models`): every job with its status, progress from 0 to 100%, epochs, losses, heartbeat, elapsed time, limits, spend, alerts, log and the actions its state allows, plus the honest status of the Stage 17 candidate. The screen only reads and passes on requests, so the browser may close.
- Acceptance on the real dataset with real processes: a stopped, a paused and a killed worker's job each ended with the same losses and the same checkpoint SHA-256 as an uninterrupted job, which also equals the Stage 16 training.
- Contracts 0.16.0: `JobRequest`, `JobEstimate`, `JobStatus`, `JobView`, `JobLogLine`, `JobDetail`; the training run purpose `job`.

### Changed — 2026-11-05 (Stage 18)

- The overview page no longer calls finished phases planned: data is done outside this app, and the models are in review, research only.

### Added — 2026-11-05 (Stage 17)

- Probabilistic evaluation (ADR-0025) under a protocol locked before anything was scored (`data/protocols/stage-17-evaluation.json`): development years 2020–2023 choose the model, final years 2024–2026 give the verdict, and an approval rule is written down in advance. The final years were never used for a choice, but they were part of the pooled test tables of Stages 15 and 16, and the package says so.
- The temporal model with seven quantiles (0.05 to 0.95); three levels still reproduce the Stage 16 checkpoints byte for byte.
- Measures (`multiverse_forecast.probabilistic`): pinball, weighted interval score, coverage and width of the 50, 80 and 90% intervals, reliability, conformalized quantile regression on the watch firms, firm-bootstrap intervals; all in each target's training space.
- Baseline bands on the same split (`multiverse_forecast.bands`): persistence, ElasticNet and boosting with the quantiles of their errors, and quantile gradient boosting, the fair rival.
- 259 GPU trainings, 9 ablations, slices by year, sector, history length and input condition, errors by firm, memorization and stability checks (`python -m multiverse_forecast evaluate train | baselines | report`). Forecasts are stored apart from the report, and a stored variant is never trained again; every training line shows the percent of the run.
- Package `eval-20261028-b365e4a12ddb` for candidate `model-20261028-9ce4d4180aa9` (GRU, not calibrated): 3 of 15 target and horizon pairs pass the rule (operating margin h = 8, EBITDA margin h = 4 and 8). Owner sign-off pending; `docs/stages/17-evaluation-package.md`.
- Measured: raw quantiles sit within 2 to 4 points of nominal coverage except in the 2020 shock (67–78% for the 80% interval at h = 4); conformal calibration made development coverage worse (0.051 against 0.029 for 80%) and stays out of the model; the network beats the persistence band on 13 of 15 pairs in the final years, while quantile boosting is as good overall, stronger at h = 1 and weaker at h = 4 to 8; no sign of memorized firms; macro, R&D, masks and depth do not move the pinball, while the firm's own history and debt features do.
- Contracts 0.15.0: `EvaluationProtocol`, `ApprovalRule`, `EvaluationPackage`, `BandScore`, `SliceScore`, `CompanyErrors`, `AblationScore`, `MemorizationScore`, `StabilityScore`, `ApprovalRow`.

### Added — 2026-11-05 (Stage 16)

- A temporal neural network on point-in-time history (ADR-0024), not a wrapper and not trained on synthetic data: GRU with attention, and causal dilated convolutions (TCN) as the candidate. Inputs: 24 quarters by 9 channels with masks, plus the Stage 15 features; outputs: quantiles 0.1, 0.5, 0.9 for five targets at five horizons, in spaces that respect each target, without clamps.
- Sequences (`python -m multiverse_pipelines.forecastset sequences`): `fsq-20261028-80de28a4bff3`, the same 31 425 rows as Stage 15, lag 0 never; all 16 shared columns equal the Stage 15 features exactly.
- Trainings (`python -m multiverse_forecast neural`, `neural-benchmark`): Stage 15 folds, cold starts and release rule; a checkpoint, `TrainingRun` manifest, epoch log and curve per run; a saved checkpoint must reproduce the forecasts.
- Protocols `data/protocols/stage-16-temporal.json` and `stage-16-temporal-large.json`, both locked before their runs; a smoke run, a CPU run (33 trainings) and a GPU run (150 trainings on an RTX 4070 Laptop GPU).
- Benchmark `bench-20261028-f02547836d11`: on the test years 2020–2026 both networks beat persistence by MAE on 25 of 25 target and horizon pairs (22 with the 95% interval below zero) and the best baseline on 24 of 25; revenue growth at h = 4: 0.309 against 0.447 and 0.324. The median error of margins stays at persistence level, which no Stage 15 model reached. Not proven: margins of firms with $10 million or more of revenue at h = 4, 8, 12. Worse than persistence for the typical firm: debt / EBITDA at h = 1, 4, 20. Worse than boosting: revenue growth at h = 1.
- A repeat of the GPU run gave the same 150 checkpoint hashes on this machine. All 20 settings score within 0.6260–0.6434 on validation, and small networks win: more capacity does not help on these data.
- Model card `docs/stages/16-model-card.md`; training curves from the logs in `docs/stages/16-plots/`.
- Contracts 0.14.0: `SequenceManifest`, `TrainingRun`, `EpochLog`, `ForecastProtocol.repeats`.
- PyTorch 2.14.1+cu130 in the optional `ml` extra, pinned in the lock; CI installs no extras.

### Fixed — 2026-11-05 (Stage 16)

- The benchmark report lists one finding per setting: a single finding with all 20 settings exceeded the 400 characters of the contract and lost the report of the first GPU run after its trainings.
- The import smoke test checks for PyTorch in a fresh interpreter, not in the shared pytest process.

### Changed — 2026-10-31 (Stage 15 accepted)

- Stage 15 (forecasting baselines) accepted by the owner (CI run 41143679653 green).

### Added — 2026-10-31 (Stage 15)

- Forecasting baselines before any neural network (ADR-0023): one dataset, one locked protocol, seven models scored on the same rows.
- Forecasting dataset (`python -m multiverse_pipelines.forecastset build`): one row per company and forecast origin, features from the point-in-time panel at the origin (lags 1 to 8, never lag 0) and macro values available at the origin, targets as first released with their release moment; named by the SHA-256 of its CSV (`fds-20261028-d9e4acd03365`: 31 425 rows, 984 companies).
- Targets: symmetric revenue growth (between −2 and 2), operating, EBITDA and FCF margins, debt / EBITDA; undefined ratios are counted, never scored; losses and vanished revenue stay in.
- Locked protocol `data/protocols/stage-15-baselines.json`: validation 2016–2019 chooses settings, test 2020–2026 is scored once, rolling origin with yearly refits on targets released before the fold year, 20% of firms held out as cold starts, train-only winsorizing, imputation and scaling.
- Models (`python -m multiverse_forecast benchmark`): persistence, seasonal naive, sector average, a pooled dynamic panel (OLS with SIC division effects and macro controls), Ridge, ElasticNet and histogram gradient boosting; MAE, RMSE, median AE, WAPE, firm- and revenue-weighted MAE, change against persistence with 95% intervals from a bootstrap over firms, errors by SIC division, the largest errors and plain findings; for all rows and for firms with $10 million or more of revenue at the origin.
- Benchmark `bench-20261028-641a5b7181ea`: revenue growth beats persistence on every horizon and measure (h = 4: MAE 0.324 against 0.447, −27.5% with the interval −29.9 to −24.9%); for margins and debt / EBITDA the lower MAE of the learned models comes from the extremes only, and for firms with material revenue no model beats persistence with its interval below zero (operating and EBITDA margins: all six worse at h = 1, 4, 12, 20).
- Contracts 0.13.0: `ForecastDatasetManifest`, `ForecastProtocol`, `BenchmarkReport` with `ScoreRow`, `SectorScore`, `ModelConfig`, `Population`.
- numpy and scikit-learn became core dependencies of `multiverse-forecast`; LightGBM stays an extra.

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
