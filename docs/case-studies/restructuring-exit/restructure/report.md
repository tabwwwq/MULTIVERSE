# ESTEE LAUDER COMPANIES INC: Workforce restructuring, 20 quarters from 2026-11-06

> **Conditional on the assumed model, not validated: model values, not market values, and no causal effect.**

Report `rep-20261106-82767eb1bea7` from run `sim-20261106-4c7780e9f423`, generator `report-studio-1`, contracts `0.23.0`. Company `377edc0e-2670-5ae1-b178-17ad4fc5cff0`, cutoff 2026-11-06, evidence level `conditional_simulation`.

## 1. Scenario objective

What would the decision below, Workforce restructuring, change for ESTEE LAUDER COMPANIES INC over the next 20 quarters, compared with the same company without it, under the same shocks?

3000 [C1] paired paths, seed 20261107 [C2]. Each path runs the company twice, with and without the decision, on the same draw of shocks, so the difference is not noise between two draws.


## 2. Historical cutoff

Only what was public by 2026-11-06 [C3] is used. The opening balance is the last quarter reported by then, 2026-09-30 [C4]; the paths start after it.


## 3. Source coverage

The case reads 8 reported quarters (S12, S13, S14, S15). Shocks come from 61 [C5] past quarters of 573 [C6] firms of the same division.

*Quarters of the case and the filing each one comes from*

| Quarter | Period end | Filed | Revenue | EBITDA | FCF | Source |
|---|---|---|---|---|---|---|
| 2024 Q4 | 2024-12-31 | 2026-02-05 | yes | yes | yes | S12 |
| 2025 Q1 | 2025-03-31 | 2026-05-01 | yes | yes | yes | S13 |
| 2025 Q2 | 2025-06-30 | 2026-08-19 | yes | yes | yes | S14 |
| 2025 Q3 | 2025-09-30 | 2026-11-03 | yes | yes | yes | S15 |
| 2025 Q4 | 2025-12-31 | 2026-02-05 | yes | yes | yes | S12 |
| 2026 Q1 | 2026-03-31 | 2026-05-01 | yes | yes | yes | S13 |
| 2026 Q2 | 2026-06-30 | 2026-08-19 | yes | yes | yes | S14 |
| 2026 Q3 | 2026-09-30 | 2026-11-03 | yes | yes | yes | S15 |


## 4. Action definition

Decision type: Workforce restructuring. The fields below are the decision exactly as the run used it (S7); ranges are drawn on every path.

*The decision*

| Field | Value |
|---|---|
| magnitude.value | -0.15 |
| magnitude.unit | fraction_of_headcount |
| timing.announcement_date | 2026-12-01 |
| timing.effective_date | 2027-01-01 |
| timing.lag_quarters | 1 |
| timing.ramp_quarters | 2 |
| payroll_to_revenue | 0.25 |
| one_off_cost_months.shape | triangular |
| one_off_cost_months.low | 2 |
| one_off_cost_months.mode | 4 |
| one_off_cost_months.high | 8 |
| savings_realization.shape | triangular |
| savings_realization.low | 0.5 |
| savings_realization.mode | 0.7 |
| savings_realization.high | 0.9 |
| productivity_loss.shape | triangular |
| productivity_loss.low | 0 |
| productivity_loss.mode | 0.03 |
| productivity_loss.high | 0.1 |
| financing.cash | 1 |
| financing.debt | 0 |
| financing.equity | 0 |


## 5. Forecast and finance model

Central path. Growth: Transparent rule: the last reported growth decays to the firm's own mean, at the persistence of the shocks. Growth is not signed for any use. Margin: Median of live-20261106-95a7dc72f773 at 4 and 8 quarters, research only; straight lines from the last four quarters, flat after 8 quarters. (S6)

Finance: the statement engine 0.4.0 (S8) turns each path into reconciled statements and a model DCF. Simulation 0.1.0 (S9).

Shocks: Innovations of a pooled AR(1) on firm-demeaned symmetric growth and on deseasonalized EBITDA margin, winsorized at 1%. Sector columns are the cross-section median of division D; firm columns are what remains. Macro columns are quarterly changes of the 3-month Treasury yield and of annual GDP growth (World Bank, CC BY 4.0). Rows end at the origin.

Dataset fds-20261106-05c19bb5643a (S5).


## 6. Results

The median model enterprise value is USD bn 23.4 [C7] without the decision and USD bn 27.9 [C8] with it. Path by path, the change has a median of USD bn 4.8 [C10], from 3.6 [C9] at p10 to 6.4 [C11] at p90.

A covenant breach happens on 48.1% [C12] of the paths with the decision. Conditional on the assumed model, not validated.

*Quantiles across paths, by quarter after the cutoff, USD bn*

| Metric | Scenario | Quarter | p10 | p50 | p90 |
|---|---|---|---|---|---|
| Revenue | Baseline | 2027 Q3 | 3.3 | 3.9 | 4.3 |
| Revenue | Baseline | 2028 Q3 | 3.3 | 4.0 | 4.7 |
| Revenue | Baseline | 2031 Q3 | 3.3 | 4.5 | 5.9 |
| Revenue | With the decision | 2027 Q3 | 3.3 | 3.9 | 4.3 |
| Revenue | With the decision | 2028 Q3 | 3.3 | 4.0 | 4.7 |
| Revenue | With the decision | 2031 Q3 | 3.3 | 4.5 | 5.9 |
| EBITDA (calculated) | Baseline | 2027 Q3 | 0.1 | 0.6 | 0.8 |
| EBITDA (calculated) | Baseline | 2028 Q3 | 0.1 | 0.6 | 0.9 |
| EBITDA (calculated) | Baseline | 2031 Q3 | 0.2 | 0.7 | 1.1 |
| EBITDA (calculated) | With the decision | 2027 Q3 | 0.2 | 0.7 | 0.9 |
| EBITDA (calculated) | With the decision | 2028 Q3 | 0.3 | 0.7 | 1.0 |
| EBITDA (calculated) | With the decision | 2031 Q3 | 0.3 | 0.8 | 1.2 |
| FCFF (unlevered, model) | Baseline | 2027 Q3 | 0.0 | 0.3 | 0.6 |
| FCFF (unlevered, model) | Baseline | 2028 Q3 | −0.0 | 0.3 | 0.7 |
| FCFF (unlevered, model) | Baseline | 2031 Q3 | −0.2 | 0.4 | 0.9 |
| FCFF (unlevered, model) | With the decision | 2027 Q3 | −0.1 | 0.2 | 0.5 |
| FCFF (unlevered, model) | With the decision | 2028 Q3 | 0.1 | 0.4 | 0.7 |
| FCFF (unlevered, model) | With the decision | 2031 Q3 | −0.1 | 0.5 | 1.0 |
| Net debt | Baseline | 2027 Q3 | 2.2 | 2.6 | 3.4 |
| Net debt | Baseline | 2028 Q3 | 1.0 | 1.6 | 2.9 |
| Net debt | Baseline | 2031 Q3 | −3.4 | −1.5 | 0.8 |
| Net debt | With the decision | 2027 Q3 | 2.4 | 2.7 | 3.5 |
| Net debt | With the decision | 2028 Q3 | 0.8 | 1.5 | 2.8 |
| Net debt | With the decision | 2031 Q3 | −4.5 | −2.6 | −0.2 |

*Model values at the cutoff, USD bn*

| Value | Scenario | p10 | p50 | p90 | Undefined on |
|---|---|---|---|---|---|
| Enterprise value (DCF, model) | Baseline | 13.2 | 23.4 | 33.0 | 4.1% |
| Equity value (model) | Baseline | 9.7 | 19.8 | 29.4 | 4.1% |
| Enterprise value (DCF, model) | With the decision | 16.1 | 27.9 | 38.8 | 1.4% |
| Equity value (model) | With the decision | 12.6 | 24.3 | 35.2 | 1.4% |
| Paired change of enterprise value | With the decision | 3.6 | 4.8 | 6.4 | 4.1% |

*Share of paths with each event within the horizon*

| Event | Scenario | Share | Monte Carlo error | Upper 95% |
|---|---|---|---|---|
| Funding shortfall: cash and the revolver do not cover needs | Baseline | 0.0% | 0.0% | 0.1% |
| Covenant breach in any quarter | Baseline | 56.3% | 0.9% | 58.1% |
| Cash below its minimum in any quarter | Baseline | 0.0% | 0.0% | 0.1% |
| Negative operating FCFF over four quarters in a row | Baseline | 25.5% | 0.8% | 27.1% |
| Funding shortfall: cash and the revolver do not cover needs | With the decision | 0.0% | 0.0% | 0.1% |
| Covenant breach in any quarter | With the decision | 48.1% | 0.9% | 49.9% |
| Cash below its minimum in any quarter | With the decision | 0.0% | 0.0% | 0.1% |
| Negative operating FCFF over four quarters in a row | With the decision | 15.0% | 0.7% | 16.4% |


## 7. Causal status

No causal effect is estimated here. The feasibility study of Stage 20 found none of its 24 pairs of method and decision feasible on the data. The difference between the two scenarios is the assumed mechanics of the decision run through the same shocks, not an effect measured on companies that made it.

Evidence level: conditional simulation.


## 8. Assumptions

17 inputs: 6 observed in filings, 1 implied from them, 1 from a model and 9 assumed.

*How each input is known*

| Input | Known as | Note |
|---|---|---|
| revenue | observed | SEC filings public at the cutoff. |
| ebitda | observed | Operating income + D&A, calculated. |
| cash | observed | Last balance sheet public at the cutoff. |
| debt | observed | Last balance sheet public at the cutoff. |
| capex_ratio | observed | Last four quarters. |
| rd_ratio | observed | Last four quarters; 0 if not reported. |
| ebitda_margin_path | model | Model median at 4 and 8 quarters, research only; interpolated, then flat. |
| growth_path | assumed | Transparent rule; the model is not signed for growth. |
| ppe | implied | D&A of the last year over an assumed 12.5% rate. |
| trade_nwc | assumed | 12% of annualized revenue: the warehouse holds no working capital. |
| goodwill | assumed | Zero: not in the warehouse. It moves book equity and gains, not cash. |
| interest_rate | assumed | 3-month Treasury + 2 points, 30% floating: interest is not in the warehouse. |
| liquidity | assumed | Minimum cash 2% and revolver 5% of revenue; covenants 3.5x and 3x. |
| deal_accounting | assumed | The target moves with the company; 15% PP&E, 25% intangibles over 10 years. |
| tax_rate | assumed | 23%. |
| dividend_payout | assumed | 25% of net income. |
| capital_cost | assumed | ERP 5%, beta 1, debt weight 15%, growth 2.5%; 10-year Treasury observed. |


## 9. Sensitivity

The same decision with one choice of the shock model changed, on fewer paths (S7). EBITDA is at the last quarter, with the decision.

*Sensitivity to the shock model, USD bn*

| Variant | Paths | EBITDA p10 | EBITDA p50 | EBITDA p90 | EV change p50 | Covenant breach |
|---|---|---|---|---|---|---|
| As run | 1000 | 0.3 | 0.8 | 1.2 | 4.9 | 47.1% |
| Mean block of 2 quarters | 1000 | 0.3 | 0.8 | 1.2 | 5.0 | 47.3% |
| Mean block of 8 quarters | 1000 | 0.3 | 0.8 | 1.2 | 5.0 | 46.5% |
| All shocks 25% larger | 1000 | 0.2 | 0.8 | 1.4 | 4.9 | 57.5% |
| Macro columns locked | 1000 | 0.3 | 0.8 | 1.2 | 4.9 | 47.1% |


## 10. Limitations

Probabilities and quantiles are conditional on the assumed model: they are not calibrated and are not confidence intervals.

Enterprise and equity values come from a model DCF: they are model values, not market values, and no price per share is given.

Where the filings do not give an input, the case implies or assumes it, and the assumptions section lists each one.

Shocks are blocks of past quarters drawn again: a crisis unlike any of them is not in the paths.

Shocks met a hard bound in 0.0% of quarters. Enterprise value is undefined on 2.8% of paths: the values table counts them.


## Claims

| Claim | Statement | Value | Unit | Pointer | Sources |
|---|---|---|---|---|---|
| C1 | Paths simulated | 3000 | paths | `/report/diagnostics/paths` | S7 |
| C2 | Seed of the run | 20261107 | count | `/report/manifest/settings/seed` | S7 |
| C3 | Knowledge cutoff | 2026-11-06 | date | `/case/as_of` | S1 |
| C4 | Opening balance date | 2026-09-30 | date | `/case/balance_date` | S1 |
| C5 | Quarters of shock history | 61 | quarters | `/report/diagnostics/history_quarters` | S1 |
| C6 | Firms behind the sector columns | 573 | count | `/case/shocks/peers` | S1 |
| C7 | Median model EV without the decision | 23380813885.88 | usd | `/report/values/0/p50` | S7 |
| C8 | Median model EV with the decision | 27861317866.23 | usd | `/report/values/2/p50` | S7 |
| C9 | p10 of the paired EV change | 3573176404.46 | usd | `/report/values/4/p10` | S7 |
| C10 | Median paired EV change | 4823733675.83 | usd | `/report/values/4/p50` | S7 |
| C11 | p90 of the paired EV change | 6441236413.24 | usd | `/report/values/4/p90` | S7 |
| C12 | Share of paths with a covenant breach, with the decision | 0.48067 | share | `/report/risks/5/probability` | S7 |

## Sources

- **S1** SEC EDGAR filings (XBRL company facts) (data_source): `/data-catalog/sec-edgar`
- **S2** U.S. Treasury par yield curve (data_source): `/data-catalog/us-treasury`
- **S3** World Bank GDP growth, CC BY 4.0 (data_source): `/data-catalog/world-bank`
- **S4** Source: ECB statistics (features of the model) (data_source): `/data-catalog/ecb-data-portal`
- **S5** Forecasting dataset (dataset): `fds-20261106-05c19bb5643a`
- **S6** Model of the central margin path (model): `live-20261106-95a7dc72f773`
- **S7** Paired Monte Carlo run (run): `sim-20261106-4c7780e9f423`
- **S8** Financial statement engine, ADR-0029 (method): `docs/adr/0029-financial-engine.md`
- **S9** Paired Monte Carlo, ADR-0030 (method): `docs/adr/0030-paired-monte-carlo.md`
- **S10** Causal feasibility study, Stage 20 (method): `docs/stages/20-causal-research-pipeline.md`
- **S11** Report Studio, ADR-0034 (method): `docs/adr/0034-report-studio.md`
- **S12** SEC filing 0001001250-26-000006, 2024 Q4 (sec_filing): <https://www.sec.gov/Archives/edgar/data/1001250/000100125026000006/>
- **S13** SEC filing 0001001250-26-000019, 2025 Q1 (sec_filing): <https://www.sec.gov/Archives/edgar/data/1001250/000100125026000019/>
- **S14** SEC filing 0001001250-26-000041, 2025 Q2 (sec_filing): <https://www.sec.gov/Archives/edgar/data/1001250/000100125026000041/>
- **S15** SEC filing 0001001250-26-000060, 2025 Q3 (sec_filing): <https://www.sec.gov/Archives/edgar/data/1001250/000100125026000060/>
