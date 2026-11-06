# multiverse-simulation

Paired Monte Carlo (`docs/08`, Stage 22). On every path the baseline and the alternate share one draw of exogenous shocks; only the decision and its own parameters differ. Every path goes through the finance engine of Stage 21, so identities hold path by path.

| Module | Holds |
|---|---|
| `shocks` | Stationary block bootstrap of calendar quarters, AR(1) deviations |
| `paths` | A case and a draw of shocks become a finance baseline |
| `run` | Batches, one seed per path, redraw of invalid paths, checkpoints |
| `summary` | Quantiles, paired changes, risks, convergence, tails, the report |
| `example` | An invented case, SYNTHETIC |

Probabilities are conditional on the assumed model. Nothing here is calibrated against outcomes.
