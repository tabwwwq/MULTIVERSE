# Acceptance audit against docs/17 (Stage 26)

Date: 2026-11-07. Commit audited: the Stage 26 commit of this file. Each requirement of `MULTIVERSE_Documentation_Kit/docs/17_ACCEPTANCE_MATRIX.md` is marked **met** only with evidence that ran; **partial** when part of the evidence is missing; **blocked** when the data or a person the evidence needs is not available. Every partial or blocked item is in the [issue register](../security/issue-register.md) (section "Acceptance gaps").

Test counts of the final gate on 2026-11-07: pytest 1 100, vitest 4 + 296, Playwright 726 passed and 21 skipped at 1440, 768 and 390 px.

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| UX-01 | Company, date and intervention validated | met | `decisions.spec.ts`: "rejects a value above the hard limit…", "requires a unit for R&D…", "rejects an announcement before the knowledge cutoff"; error screenshots of [Stage 05](../stages/05-decision-builder.md) |
| UX-02 | Run, cancel and save survive a refresh | met | `gate-a.spec.ts` "refresh keeps the state (TC-10)"; `notebook.spec.ts` "saves … survives a refresh"; `models.spec.ts` stop and pause through the queue; the queue owns jobs, so a refresh changes nothing ([Stage 18](../stages/18-training-operations.md)) |
| UX-03 | Charts accessible as tables | partial | Every chart has "Show as table" and keyboard reading (`gate-a.spec.ts` "reaches and reads the timeline chart without a mouse", `interaction.spec.ts`); axe WCAG 2.2 on every route. No session with a live screen reader: ACC-001 |
| UX-04 | Demo and empirical labels distinguishable | met | `real.spec.ts` "keeps a fictional company marked as such"; `test_reportdoc.py` "a synthetic run cannot pose as market truth"; the badge of every page (`gate-a.spec.ts`) |
| DATA-01 | Raw SEC snapshot immutable | met | Archive with SHA-256 and metadata per file ([Stage 10](../stages/10-sec-raw-ingestion.md)); `test_pit_warehouse.py`, `test_packaging.py` |
| DATA-02 | Filed-at snapshots enforced | met | `test_pit_warehouse.py` and `test_audit.py` leakage checks: a build cut at a date equals the full build at that date byte for byte ([Stage 12](../stages/12-point-in-time-warehouse.md), [Stage 14](../stages/14-data-quality-gate.md)) |
| DATA-03 | Quarterization and restatements | met | `test_xbrl_normalize.py`: Q4 from the year, year-to-date cash flows, restatements kept beside the first value ([Stage 11](../stages/11-xbrl-normalization.md)) |
| DATA-04 | Currency, scaling, concept maps documented | met | Lineage of each value to its concept and filing; another currency refused, not converted; scale checks of the public float ([Stage 11](../stages/11-xbrl-normalization.md), [Stage 24b](../stages/24b-real-companies.md)) |
| DATA-05 | Source coverage transparent | met | Generated data card of Gate B ([Stage 14](../stages/14-data-quality-gate.md)); [data card](../governance/data-card.md); coverage in every research report |
| ML-01 | Naive, ridge and boosting on the same folds | met | Locked-protocol benchmark of seven baselines ([Stage 15](../stages/15-baseline-forecasting.md)); `test_baselines.py` |
| ML-02 | Neural network on the PIT panel | met | `bench-20261106-20302859cff2` with protocol hash, settings and checkpoints ([Stage 24b](../stages/24b-real-companies.md)); `test_neural.py`, `test_artifacts.py` |
| ML-03 | Out-of-time and company-level evaluation | met | Final years 2024–2026 and cold-start firms in `stage_24b_evaluation` ([Stage 24b](../stages/24b-real-companies.md)); `test_evaluation.py` |
| ML-04 | Bands calibrated or flagged | met | Coverage plots in [`24b-plots`](../stages/24b-plots/) and [`17-plots`](../stages/17-plots/); the screens flag the model as not approved with its measured coverage |
| ML-05 | Training stops and resumes | met | `test_resumable.py`: a stopped, paused or killed job ends with the same checkpoint as one never stopped ([Stage 18](../stages/18-training-operations.md)) |
| CAUS-01 | Precise action definitions | met | Intervention catalog with typed fields, units and ranges; `test_decisions.py`, `test_sources.py` "catalog defines exactly the fields of the model" |
| CAUS-02 | Event evidence linked to source | partial | Each event cites its filing and quote (`test_events.py` "an event needs evidence and a named review"); the review was one AI reviewer, not an independent person ([Stage 19](../stages/19-corporate-event-ontology.md)): CAUS-GAP-1 |
| CAUS-03 | Confounders and assumptions documented | met | Causal graph and assumption notes of [Stage 20](../stages/20-causal-research-pipeline.md); `test_study.py` |
| CAUS-04 | Placebo and pre-trend diagnostics | blocked | The study defines placebo dates (`test_study.py` "leads and placebo dates stay before the event"), but no design was feasible, so no diagnostic could run on an estimate: CAUS-GAP-2 |
| FIN-01 | Revenue to EBITDA to FCF reconciliation | met | `test_properties.py`, `test_engine.py`: every decision of the catalog books and reconciles; a broken statement is caught ([Stage 21](../stages/21-financial-statement-engine.md)) |
| FIN-02 | DCF and bridge correct | met | Known-answer DCF and bridge tests in `test_valuation.py` ([Stage 23](../stages/23-valuation-risk-studio.md)) |
| FIN-03 | Financing, debt and cash constraints | met | `test_stress.py`, `test_interventions.py`: revolver, covenants, financing shares exact |
| SIM-01 | Same seed, config and version reproducible | met | `test_reportdoc.py` "a report replays byte for byte from its manifest"; real Intel report replayed identically ([Stage 25](../stages/25-reports-portfolio.md)) |
| SIM-02 | Paired baseline and intervention shocks | met | `test_report.py` "a paired change is computed path by path"; `test_run.py` |
| SIM-03 | Probabilities labelled conditional | met | Contract refuses a calibrated simulation result; `launch.spec.ts` "says the run is conditional before any number"; `test_case_studies.py` |
| OPS-01 | Job idempotency and status recovery | met | `test_simulations.py` "a repeated submit gives the same job"; `test_store.py` leases and heartbeats ([Stage 18](../stages/18-training-operations.md)) |
| OPS-02 | Spend cap and cancellation | met | `test_limits.py`: cloud spend limit at submit, approval and claim; induced budget stops ([Stage 18](../stages/18-training-operations.md), [Stage 24](../stages/24-security-privacy-governance.md)) |
| SEC-01 | Restricted data never redistributed | partial | Raw files never in git (`test_packaging.py`); the public repository holds derived FRED values of Stage 22 (2 columns of 59 quarters and 2 rates): LIC-003, owner decided on 2026-11-07 to leave them for now |
| SEC-02 | Secrets absent from frontend, git and reports | met | gitleaks in CI on the whole history; local scan on 2026-11-07: 0 hits of the FRED key and the SEC User-Agent in 58 MB of history, tracked files, the web bundle and the case-study reports |
| REP-01 | Report carries provenance and versions | met | `test_case_studies.py` "the files are those the manifest hashed"; `test_reportdoc.py` manifest tests |
| REP-02 | Limitations visible at the result | partial | Limitations precede numbers on every result screen and report (`launch.spec.ts`, `valuation.spec.ts`, `reports.spec.ts`); the user study the matrix asks for has not been run: UX-GAP-1 |
| PORT-01 | Case study reproducible by a cold-start reviewer | partial | A fresh clone ran the smoke tests and replays in 148 s (59 passed, 6 skipped); a real case study replays only where its case was built from the 8.2 GB raw archive, which a reviewer must download: PORT-GAP-1 |

**Summary:** 25 met, 5 partial, 1 blocked of 31.

## Further checks of prompt 26

| Check | Result |
|---|---|
| Time zones | Desktop browser suite with `E2E_TZ=Pacific/Kiritimati` (UTC+14) and `America/Los_Angeles`: 242 passed and 7 skipped in each |
| Mobile browsers | Chromium with a 390 px touch viewport only; Safari and Firefox on phones not tested: MOB-001 |
| Loading and empty states | Covered by the e2e suites of Universe, Report Studio, Launch Center and Models (offline, empty, failed) |
| Backup and rollback | `multiverse-worker backup`, `verify`, `restore` on the real queue: 37 files, 10 jobs, 43 audit rows, 24 s |
| Dependency audit | npm runtime 0, Python 0, npm development tools 11 moderate (accepted, SEC-018) |
| Deployment logs and error budget | No deployment exists; the error budget for the local research tier is in [release criteria](release-criteria.md) |
