# Interview questions, answered from this repository

Each answer points to where the work is, so it can be shown rather than told.

**How did you prevent look-ahead bias with revised filings?**
Every value carries the moment it became public: the filing date of the 10-K or 10-Q that first reported it, and a new interval when a later filing restates it. A snapshot at a cutoff reads only intervals that had started by then, and a leakage check rebuilds the warehouse from archives cut at that date and compares byte for byte ([Stage 12](../stages/12-point-in-time-warehouse.md)). Macro series follow the same rule; World Bank series have no dated vintages, so the model never sees them ([Stage 24b](../stages/24b-real-companies.md)).

**Why GRU against boosting, and when did the simple model win?**
Baselines came first under a locked protocol. The networks beat persistence on all 25 pairs and the best baseline on 24 of them on the first universe ([Stage 16](../stages/16-temporal-neural-net.md)). On quantiles, quantile gradient boosting was as good overall ([Stage 17](../stages/17-probabilistic-validation.md)), and on the larger universe it still wins on one-quarter revenue growth, by 11.8% ([Stage 24b](../stages/24b-real-companies.md)). A transformer was not tried: the data is quarterly and short.

**What is the difference between predictive importance and a causal effect?**
A feature can predict revenue because firms that do something are already different. The feasibility study asked, before any estimate, whether the events have clean timing, enough treated firms, comparable controls and no outcome peeking; none of 24 designs passed ([Stage 20](../stages/20-causal-research-pipeline.md)). So every scenario in the app is labelled as conditional mechanics, never as an effect.

**How did you balance heterogeneous firms, sectors and fiscal calendars?**
Fiscal calendars are read from each firm's own 10-K periods, including 52/53-week years; targets are scale-free (growth, margins, debt to EBITDA); evaluation reports firm-weighted and revenue-weighted errors and a population of firms with at least USD 10m of revenue; shocks are drawn from the firm's SIC division ([Stage 11](../stages/11-xbrl-normalization.md), [Stage 15](../stages/15-baseline-forecasting.md)).

**How did you validate DCF cash-flow consistency?**
The statement engine checks on every quarter of every path that the balance sheet balances, cash moves as the cash-flow statement says and FCFF bridges from EBITDA; a path that breaks an identity is a bug and stops the run ([Stage 21](../stages/21-financial-statement-engine.md), [Stage 22](../stages/22-paired-monte-carlo.md)).

**What happens if training fails or the user closes the browser?**
Work runs in a queue with leases, heartbeats and checkpoints at each epoch or batch of paths. Closing the browser changes nothing; a stopped, paused or killed job resumes to the same checkpoint and the same numbers ([Stage 18](../stages/18-training-operations.md)).

**What assumptions would invalidate an "Apple without the iPhone" scenario?**
That the rest of the company would have stayed as it was; that shocks from the past describe a world without its main product; that the decision is a change of a few lines in the statements rather than a different firm. The engine can model an exit of a share of revenue, but such a counterfactual is far outside the history its shocks come from, and the report would have to say that the result is mechanics, not evidence.

**How would you know a report has not been edited?**
Its manifest holds the SHA-256 of each file and replays the run: `python -m multiverse_simulation replay` rebuilds Markdown, CSV and JSON and compares them byte for byte ([ADR-0034](../adr/0034-report-studio.md)).
