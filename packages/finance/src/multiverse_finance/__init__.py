"""Pure financial engine of MULTIVERSE (docs/07, whitepaper in docs/finance).

Responsibility: three linked statements from a baseline and decisions, FCFF / FCFE, WACC, DCF
and the EV -> equity bridge. No KPI is set directly: a decision compiles into ledger entries,
and every path is reconciled before it leaves ``project``.

Rules: no I/O, no web or ML frameworks; money uses decimal.Decimal; every function is
deterministic and covered by identity / property tests."""

__version__ = "0.2.0"
