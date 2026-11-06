"""Effect estimators, behind the gate of the event registry audit.

The difference-in-differences here reads outcomes after the treatment, so it refuses to run
until the audit of Stage 19 says the sample is credible. It is tested on invented data with
a known effect; nothing in this project has run it on real events.
"""

from dataclasses import dataclass

import numpy as np

from multiverse_causal.diagnostics import Treated, did, match
from multiverse_causal.panel import Panel
from multiverse_contracts.events import QualityAudit


class CausalWorkBlockedError(RuntimeError):
    """The registry audit does not allow an effect to be estimated."""


@dataclass(frozen=True)
class Estimate:
    """Never a bare number: what it is, on whom, with what uncertainty and assumptions."""

    outcome: str
    effect: float
    standard_error: float
    events: int
    data_cutoff: str
    cohort: str
    confounders: tuple[str, ...]
    untested_assumptions: tuple[str, ...]


def require_open_gate(audit: QualityAudit) -> None:
    if not audit.credible_for_causal_work:
        raise CausalWorkBlockedError("; ".join(audit.blockers) or "the audit says not credible")


def difference_in_differences(
    audit: QualityAudit,
    panel: Panel,
    events: list[Treated],
    excluded: np.ndarray,
    outcome: int,
    labels: tuple[str, str, str],
    confounders: tuple[str, ...],
    untested: tuple[str, ...],
) -> Estimate:
    require_open_gate(audit)
    effects: list[float] = []
    for event in events:
        partner = match(panel, event.firm, event.event - 1, excluded)
        if partner is None:
            continue
        value = did(panel, event.firm, partner, event.event, outcome)
        if np.isfinite(value):
            effects.append(value)
    if len(effects) < 2:
        raise ValueError("too few events with data on both sides")
    values = np.array(effects)
    name, cutoff, cohort = labels
    return Estimate(
        outcome=name,
        effect=float(values.mean()),
        standard_error=float(values.std(ddof=1) / np.sqrt(values.size)),
        events=int(values.size),
        data_cutoff=cutoff,
        cohort=cohort,
        confounders=confounders,
        untested_assumptions=untested,
    )
