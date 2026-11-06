"""Causal research tools of MULTIVERSE.

Responsibility: DAGs, estimands, identification assumptions, matching / DiD /
synthetic control prototypes, placebo and sensitivity diagnostics (docs/05).

Rule: never label a result causal without a stored diagnostics artifact. Effect estimators
stay behind the gate of the event registry audit (Stage 19).

    python -m multiverse_causal study --dataset var/data/forecast/<dataset id> ...
"""

__version__ = "0.1.0"
