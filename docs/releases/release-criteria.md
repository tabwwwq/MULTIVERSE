# Release criteria: demo, research and empirical tiers (Stage 26)

A release says which tier it is, and shows only what that tier allows. The tier is decided by evidence in this repository, not by how finished the software looks.

| Tier | What it may show | Required evidence | Status on 2026-11-07 |
|---|---|---|---|
| **Demo** | Fictional companies and mock results, marked "Synthetic" or "Demo" on every screen | Gate A ([v1 release note](v1-interactive-prototype.md)); `npm run check` green; labels tested on every route | **Met** |
| **Research preview** | Real companies from SEC filings, research forecasts and conditional simulations, each labelled "not approved" and "conditional, not validated"; runs only on the owner's machine | Everything of the demo tier; point-in-time leakage proof; locked-protocol evaluation with coverage reported; reports that replay from their manifests; security review with no open Critical issue on what is published; licences of every published source | **Met for a local release.** A public deployment is blocked by OPS-001 (no TLS) and OPS-002 (no browser login), and LIC-001 (Critical, FRED) concerns data and a model that are not published |
| **Empirical** | A forecast or an effect presented as reliable for decisions | Model approved on the pairs it shows by the rule written before scoring; calibrated coverage on held-out years and firms; an estimated causal effect with diagnostics for any claim of effect; an independent review | **Not met.** 2 of 15 pairs pass the approval rule; no causal design was feasible (Stage 20). Nothing may be released in this tier |

## Rules

1. **The empirical model is not validated, so no release presents forecasts or scenarios as empirical.** Screens and reports keep the labels "Research forecast, not approved for the product" and "Conditional on the assumed model, not validated".
2. **A public deployment shows the demo tier only** until OPS-001 and OPS-002 are closed: fictional companies, mock results, and the static research documents (case studies, model and data cards). The research preview stays local (`npm run app`).
3. **No release contains** raw source files, the warehouse, checkpoints or FRED content (`tests/smoke/test_packaging.py`).
4. **Every release** runs `npm run check` green, CI green on the release commit, and records its version in `CHANGELOG.md` and a release note.

## Error budget of the local research tier

There is no service level for users, because there are no users and no deployment. For the owner's machine:

| Measure | Budget | How it is checked |
|---|---|---|
| Quality gate | 0 failing tests on `main`; a flaky test is fixed or quarantined within one stage | `npm run check`, CI |
| Jobs | A failed job carries its reason; no job is lost by a closed browser, a stop or a crash | Queue tests; `multiverse-worker status` |
| Reports | 0 replays that differ from their manifest | `python -m multiverse_simulation replay` |
| Backups | A backup verifies before any upgrade | `multiverse-worker backup` and `verify` |

Deployment logs: none exist, because nothing has been deployed.
