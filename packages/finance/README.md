# multiverse-finance

Pure financial engine (`docs/07`, Stage 21): a baseline and decisions become three linked statements, then FCFF, WACC, DCF and the EV → equity bridge. No KPI is set directly, and `project` refuses a path that does not reconcile. Method and limits: [whitepaper](../../docs/finance/financial-engine-whitepaper.md).

Rules: no I/O, no web or ML frameworks, `decimal.Decimal` for money, deterministic functions with identity and property tests.

| Module | Holds |
|---|---|
| `exact` | Decimal context, refusal of bad numbers, undefined ratios |
| `schedules` | Time lags: ramp, shift, spread |
| `model` | Opening balance sheet, policy, baseline drivers |
| `ledger` | Entries a decision leaves in the books, funding tables |
| `engine` | `project`: quarter after quarter, the liquidity waterfall |
| `statements` | Income, cash flow, balance, free cash, credit |
| `checks` | Every identity as a residual |
| `interventions` | Event accounting of the six decisions |
| `decisions` | A decision of the contract at its central values |
| `valuation` | WACC, DCF, bridge |
| `stress` | Stress cases as changes of the baseline |
| `example` | An invented company, SYNTHETIC |
