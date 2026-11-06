"""The causal hypothesis of the project (docs/05): a graph, estimands and assumptions.

The graph comes from reasoning about firms, not from data: it says what would have to hold,
and which variables nothing here can see. Expectations of management (U) drive both the
decision and the outcome and are unobserved, which is why no method below can be simply
trusted: every design needs its assumptions stated and its diagnostics stored.
"""

from multiverse_contracts.causal import CausalEdge, CausalGraph, CausalNode
from multiverse_contracts.events import EventType

NODES = (
    CausalNode(
        node_id="macro",
        label="Macro conditions",
        role="macro",
        observed=True,
        measured_by="Macro vintages at the origin (Stage 13).",
    ),
    CausalNode(
        node_id="firm_state",
        label="Firm state before the decision",
        role="state",
        observed=True,
        measured_by="Size, margins, growth, debt, cash and intensities at the last origin before.",
    ),
    CausalNode(
        node_id="expectations",
        label="Management expectations",
        role="unobserved",
        observed=False,
        measured_by="Nothing here: plans and private forecasts are not in filings.",
    ),
    CausalNode(
        node_id="action",
        label="Decision",
        role="action",
        observed=True,
        measured_by="The verified event registry (Stage 19).",
    ),
    CausalNode(
        node_id="other_decisions",
        label="Other decisions at the same time",
        role="state",
        observed=True,
        measured_by="Confounders named in documents, and 8-K items of the filing index.",
    ),
    CausalNode(
        node_id="costs",
        label="Costs and capacity",
        role="mediator",
        observed=True,
        measured_by="Margins and capital intensity after the decision.",
    ),
    CausalNode(
        node_id="demand",
        label="Demand for the firm",
        role="mediator",
        observed=False,
        measured_by="Not measured directly; revenue mixes it with price and competition.",
    ),
    CausalNode(
        node_id="outcome",
        label="Revenue growth and margins",
        role="outcome",
        observed=True,
        measured_by="Point-in-time quarterly values in the forecasting dataset (Stage 15).",
    ),
)
EDGES = (
    CausalEdge(
        source="macro",
        target="action",
        rationale="Credit and demand conditions shape what firms decide.",
    ),
    CausalEdge(
        source="macro", target="outcome", rationale="A recession moves results of every firm."
    ),
    CausalEdge(
        source="macro",
        target="firm_state",
        rationale="Past conditions are already in the balance sheet.",
    ),
    CausalEdge(
        source="firm_state",
        target="action",
        rationale="Weak firms cut staff, cash-rich firms buy: decisions follow the state.",
    ),
    CausalEdge(
        source="firm_state",
        target="outcome",
        rationale="Growth and margins persist and revert by themselves.",
    ),
    CausalEdge(
        source="expectations",
        target="action",
        rationale="Managers act on what they expect and outsiders cannot see.",
    ),
    CausalEdge(
        source="expectations",
        target="outcome",
        rationale="What they expect tends to happen, with or without the decision.",
    ),
    CausalEdge(
        source="firm_state",
        target="other_decisions",
        rationale="The same state triggers several decisions at once.",
    ),
    CausalEdge(
        source="other_decisions",
        target="outcome",
        rationale="A merger and a layoff in one year cannot be told apart by their results.",
    ),
    CausalEdge(
        source="action", target="costs", rationale="Most decisions change costs or capacity first."
    ),
    CausalEdge(
        source="action", target="demand", rationale="Products and reach change what customers buy."
    ),
    CausalEdge(source="costs", target="outcome", rationale="Costs reach margins with a lag."),
    CausalEdge(source="demand", target="outcome", rationale="Demand reaches revenue with a lag."),
)
OMITTED = (
    "Competitors' moves and market structure.",
    "Management quality and turnover.",
    "Accounting choices around a decision, such as restructuring charges.",
    "Effects on other firms: a rival's layoff or merger is not independent of this one.",
)
GRAPH = CausalGraph(nodes=NODES, edges=EDGES, omitted=OMITTED)

COMMON = (
    "Conditional parallel trends: without the action, treated firms would have moved like "
    "their matched controls.",
    "No anticipation before the first public document.",
    "Overlap: firms like the treated also exist without the action.",
    "One version of the treatment: the same label means the same action.",
    "No interference between firms.",
)
UNTESTED = (
    "Management expectations are not measured: pre-trends can look fine and still be driven "
    "by a plan outsiders cannot see.",
    "Parallel trends after the event can never be tested, only made plausible before it.",
    "No interference between firms is assumed, not checked.",
)
ESTIMANDS: dict[EventType, str] = {
    EventType.ACQUISITION: "Average effect on firms that closed an acquisition, on growth and "
    "margins 4 to 7 quarters after the first public document, against matched firms without one.",
    EventType.DIVESTITURE: "Average effect on firms that sold or spun off a business, on growth "
    "and margins 4 to 7 quarters after, against matched firms without one.",
    EventType.LAYOFF: "Average effect on firms that announced a workforce reduction, by intention "
    "to treat, on margins and growth 4 to 7 quarters after, against matched firms without one.",
    EventType.REFINANCING: "Average effect on firms that replaced or amended debt, on margins and "
    "growth 4 to 7 quarters after, against matched firms without one.",
    EventType.RND_CHANGE: "Average effect of a yearly change of R&D expense on growth and margins "
    "4 to 7 quarters after it was reported, against matched firms without such a change.",
    EventType.CAPEX_CHANGE: "Average effect of a yearly change of capital expenditure on growth "
    "and margins 4 to 7 quarters after it was reported, against matched firms without one.",
}
EXTRA: dict[EventType, tuple[str, ...]] = {
    EventType.ACQUISITION: ("The target's results enter the buyer's: growth is not organic.",),
    EventType.DIVESTITURE: ("Revenue falls by construction when a business leaves.",),
    EventType.LAYOFF: ("Firms cut staff because results are falling: reversion to the mean.",),
    EventType.REFINANCING: ("Debt is often raised for another decision, not for itself.",),
    EventType.RND_CHANGE: ("Effects of R&D may take longer than any window here.",),
    EventType.CAPEX_CHANGE: ("A rise can be a finished project, not a decision of that year.",),
}
RULES = (
    "Audit: no effect is estimated until the event registry audit says credible.",
    "Sample: at least 30 usable events for matched, weighted and event-study designs.",
    "Support: at least 90% of treated firms inside the controls' propensity range.",
    "Balance: every standardized mean difference at most 0.25 after matching.",
    "Pre-trends: at most one lead per outcome with its 95% interval away from zero.",
    "Placebo dates: at most one in ten away from zero.",
    "Null: at most 10% of pseudo-event draws rejected at a nominal 5%.",
    "Synthetic control: half of the events usable, holdout error at most 1.5 times the fit.",
)
