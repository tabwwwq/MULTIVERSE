# Resume bullets

Each bullet is flagged. **After implemented: yes** means the work exists in this repository and every number in the bullet comes from the linked report. Bullets about things not built are not written.

| Bullet | After implemented | Evidence |
|---|---|---|
| Built an end-to-end research platform for counterfactual corporate scenarios: SEC XBRL ingestion, a point-in-time warehouse, forecasting, a three-statement engine, paired Monte Carlo and a web app | yes | [Portfolio](README.md) |
| Designed a point-in-time warehouse of 1 429 companies and 6.5 million value intervals, rebuilt from immutable archives with a byte-for-byte leakage check | yes | [Stage 24b](../stages/24b-real-companies.md), [Stage 12](../stages/12-point-in-time-warehouse.md) |
| Benchmarked GRU and temporal convolutional networks against seven statistical baselines under protocols locked before scoring; on 2020–2026 the network cut the error of 4-quarter revenue growth forecasts by 31.7% against persistence and 4.7% against the best baseline | yes | [Stage 24b](../stages/24b-real-companies.md) |
| Evaluated quantile forecasts on held-out years: 80% ranges held 82.2% of outcomes for 4-quarter revenue growth; reported that only 2 of 15 target and horizon pairs met the approval rule | yes | [Stage 24b](../stages/24b-real-companies.md) |
| Ran a causal feasibility study before any estimate and reported that none of 24 designs was feasible, keeping every scenario labelled as conditional | yes | [Stage 20](../stages/20-causal-research-pipeline.md) |
| Developed an accounting-consistent Monte Carlo engine whose every path reconciles three statements, FCFF and a model DCF | yes | [Stage 21](../stages/21-financial-statement-engine.md), [Stage 22](../stages/22-paired-monte-carlo.md) |
| Built reproducible research reports whose every number points into the run and whose manifest replays them byte for byte | yes | [Stage 25](../stages/25-reports-portfolio.md) |
| Secured a local research API: token roles, object ownership, queue-enforced spending limits, an audit log and a 36-issue security and licence review | yes | [Stage 24](../stages/24-security-privacy-governance.md) |

Not claimed anywhere: users, revenue, return on investment, production deployment, or accuracy beyond the held-out years of these reports.
