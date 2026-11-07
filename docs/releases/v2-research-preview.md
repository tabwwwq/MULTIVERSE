# Release note — v2 research preview

| Field | Value |
|---|---|
| Version | v2.0.0-research (git tag) |
| Date | 2026-11-07 |
| Tier | Research preview, local only ([release criteria](release-criteria.md)); the empirical tier is not met |
| Published | Tag on GitHub, approved by the owner on 2026-11-07: <https://github.com/tabwwwq/MULTIVERSE/tree/v2.0.0-research>. No hosted site and no GitHub Release page |
| Previous release | [v1 interactive prototype](v1-interactive-prototype.md) (demo tier) |

## Supported features

| Feature | Where | Data |
|---|---|---|
| Universe of the 500 largest SEC filers by public float, then 7 fictional companies | `/universe` | Real (SEC) and synthetic, labelled |
| Company dossier with lineage to filings and a cutoff | `/dossier/<id>` | Real and synthetic |
| Research forecast: p10, p50, p90 of five measures at 1, 4 and 8 quarters | Dossier of 496 real companies | Model without FRED, not approved |
| Decision Builder: six decision types, validation, units, ranges | `/decisions` | — |
| Run of a decision: estimate, approval, queue, progress, result | Run dialog, `/run` | 373 real companies with a case; needs `npm run app` |
| Launch Center, Valuation Studio, Risk Observatory on the Stage 22 case | `/launch`, `/valuation`, `/risk` | Hubbell case derived from FRED (LIC-003) |
| Report Studio: Markdown, CSV, JSON, print to PDF, manifest, replay | `/reports`, `python -m multiverse_simulation replay` | Every finished run |
| Training jobs with estimates, budgets, stop, pause and resume | `/models`, `multiverse-worker` | Local GPU or CPU |
| Research notebook on this device | `/notebook` | Browser storage |
| Data Catalog, methodology, event registry, causal map | `/data-catalog`, `/methodology`, `/events`, `/causal-map` | Documentation and study results |

Not supported: a hosted service, accounts in the browser, market prices, a price per share, causal effects, companies without a 10-K, simulations of banks and insurers.

## Evidence

- Final gate of Stage 26: pytest 1 100, vitest 4 + 296, Playwright 726 passed and 21 skipped; CI run 42409086930 green 8/8 on `22f45f0` ([Stage 26](../stages/26-final-review.md)).
- [Acceptance audit](acceptance-audit.md): 25 of 31 requirements met, 5 partial, 1 blocked.
- A fresh clone ran its smoke tests and report replays in 148 s.

## Measured model performance

On the test years 2020–2026 the model without FRED forecasts revenue growth over 4 quarters with an MAE 31.7% below persistence (29.9 to 33.4%) and 4.7% below the best baseline; over 1 quarter it is 11.8% worse than gradient boosting. Its p10–p90 ranges held 82.2% of outcomes for 4-quarter revenue growth on 2024–2026 against 80% stated; 2 of 15 target and horizon pairs pass the approval rule ([Stage 24b](../stages/24b-real-companies.md)).

## Limitations and blockers

- Not validated for decisions: the empirical tier is not met.
- No causal effect is estimated anywhere.
- Public deployment blocked by OPS-001 (TLS) and OPS-002 (browser login).
- FRED: LIC-001 (Critical), LIC-002, LIC-003 open; the owner chose to keep the data for now.
- Acceptance gaps ACC-001, UX-GAP-1, CAUS-GAP-1, CAUS-GAP-2, PORT-GAP-1, MOB-001.
- No LICENSE file (LIC-006): all rights reserved by default.

## Maintenance

[Runbook](runbook.md) · [Support](../../SUPPORT.md) · [Model card](../governance/model-card.md) · [Data card](../governance/data-card.md) · [Source card](../governance/source-card.md)
