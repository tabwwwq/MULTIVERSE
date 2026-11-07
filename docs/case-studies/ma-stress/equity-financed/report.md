# BOEING CO: Acquisition, 20 quarters from 2026-11-06

> **Conditional on the assumed model, not validated: model values, not market values, and no causal effect.**

Report `rep-20261106-aa2c0d7cf295` from run `sim-20261106-40dd0a976124`, generator `report-studio-1`, contracts `0.23.0`. Company `4bfbd7a0-568c-5050-b209-dab6d39235b1`, cutoff 2026-11-06, evidence level `conditional_simulation`.

## 1. Scenario objective

What would the decision below, Acquisition, change for BOEING CO over the next 20 quarters, compared with the same company without it, under the same shocks?

3000 [C1] paired paths, seed 20261107 [C2]. Each path runs the company twice, with and without the decision, on the same draw of shocks, so the difference is not noise between two draws.


## 2. Historical cutoff

Only what was public by 2026-11-06 [C3] is used. The opening balance is the last quarter reported by then, 2026-09-30 [C4]; the paths start after it.


## 3. Source coverage

The case reads 8 reported quarters (S12, S13, S14, S15). Shocks come from 67 [C5] past quarters of 573 [C6] firms of the same division.

*Quarters of the case and the filing each one comes from*

| Quarter | Period end | Filed | Revenue | EBITDA | FCF | Source |
|---|---|---|---|---|---|---|
| 2024 Q4 | 2024-12-31 | 2026-01-30 | yes | yes | yes | S12 |
| 2025 Q1 | 2025-03-31 | 2026-04-22 | yes | yes | yes | S13 |
| 2025 Q2 | 2025-06-30 | 2026-07-28 | yes | yes | yes | S14 |
| 2025 Q3 | 2025-09-30 | 2026-10-27 | yes | yes | yes | S15 |
| 2025 Q4 | 2025-12-31 | 2026-10-27 | yes | yes | yes | S15 |
| 2026 Q1 | 2026-03-31 | 2026-04-22 | yes | yes | yes | S13 |
| 2026 Q2 | 2026-06-30 | 2026-07-28 | yes | yes | yes | S14 |
| 2026 Q3 | 2026-09-30 | 2026-10-27 | yes | yes | yes | S15 |


## 4. Action definition

Decision type: Acquisition. The fields below are the decision exactly as the run used it (S7); ranges are drawn on every path.

*The decision*

| Field | Value |
|---|---|
| magnitude.value | 15000000000 |
| magnitude.unit | usd |
| timing.announcement_date | 2026-12-01 |
| timing.effective_date | 2027-01-01 |
| timing.lag_quarters | 2 |
| timing.ramp_quarters | 8 |
| target_revenue | 6000000000 |
| target_ebitda_margin | 0.15 |
| deal_cost_fraction | 0.02 |
| integration_cost_fraction.shape | triangular |
| integration_cost_fraction.low | 0.02 |
| integration_cost_fraction.mode | 0.05 |
| integration_cost_fraction.high | 0.1 |
| cost_synergy_fraction.shape | triangular |
| cost_synergy_fraction.low | 0 |
| cost_synergy_fraction.mode | 0.03 |
| cost_synergy_fraction.high | 0.06 |
| completion_probability | 0.9 |
| new_debt_interest_rate | 0.065 |
| financing.cash | 0.1 |
| financing.debt | 0.4 |
| financing.equity | 0.5 |


## 5. Forecast and finance model

Central path. Growth: Transparent rule: the last reported growth decays to the firm's own mean, at the persistence of the shocks. Growth is not signed for any use. Margin: Median of live-20261106-95a7dc72f773 at 4 and 8 quarters, research only; straight lines from the last four quarters, flat after 8 quarters. (S6)

Finance: the statement engine 0.4.0 (S8) turns each path into reconciled statements and a model DCF. Simulation 0.1.0 (S9).

Shocks: Innovations of a pooled AR(1) on firm-demeaned symmetric growth and on deseasonalized EBITDA margin, winsorized at 1%. Sector columns are the cross-section median of division D; firm columns are what remains. Macro columns are quarterly changes of the 3-month Treasury yield and of annual GDP growth (World Bank, CC BY 4.0). Rows end at the origin.

Dataset fds-20261106-05c19bb5643a (S5).


## 6. Results

The median model enterprise value is USD bn 93.3 [C7] without the decision and USD bn 87.7 [C8] with it. Path by path, the change has a median of USD bn −3.9 [C10], from −6.6 [C9] at p10 to −0.2 [C11] at p90.

A covenant breach happens on 99.5% [C12] of the paths with the decision. Conditional on the assumed model, not validated.

*Quantiles across paths, by quarter after the cutoff, USD bn*

| Metric | Scenario | Quarter | p10 | p50 | p90 |
|---|---|---|---|---|---|
| Revenue | Baseline | 2027 Q3 | 19.4 | 25.2 | 31.2 |
| Revenue | Baseline | 2028 Q3 | 17.8 | 25.9 | 34.2 |
| Revenue | Baseline | 2031 Q3 | 15.9 | 28.3 | 43.7 |
| Revenue | With the decision | 2027 Q3 | 20.7 | 26.5 | 32.6 |
| Revenue | With the decision | 2028 Q3 | 19.1 | 27.3 | 35.8 |
| Revenue | With the decision | 2031 Q3 | 16.9 | 29.8 | 46.1 |
| EBITDA (calculated) | Baseline | 2027 Q3 | −2.2 | 3.1 | 4.9 |
| EBITDA (calculated) | Baseline | 2028 Q3 | −2.3 | 3.0 | 5.1 |
| EBITDA (calculated) | Baseline | 2031 Q3 | −2.4 | 3.1 | 6.4 |
| EBITDA (calculated) | With the decision | 2027 Q3 | −2.5 | 2.9 | 4.7 |
| EBITDA (calculated) | With the decision | 2028 Q3 | −2.2 | 3.1 | 5.2 |
| EBITDA (calculated) | With the decision | 2031 Q3 | −2.3 | 3.4 | 6.8 |
| FCFF (unlevered, model) | Baseline | 2027 Q3 | −3.0 | 1.5 | 3.5 |
| FCFF (unlevered, model) | Baseline | 2028 Q3 | −3.3 | 1.5 | 4.8 |
| FCFF (unlevered, model) | Baseline | 2031 Q3 | −4.8 | 1.4 | 7.2 |
| FCFF (unlevered, model) | With the decision | 2027 Q3 | −17.8 | −13.4 | −5.8 |
| FCFF (unlevered, model) | With the decision | 2028 Q3 | −3.4 | 1.5 | 5.1 |
| FCFF (unlevered, model) | With the decision | 2031 Q3 | −4.7 | 1.6 | 7.7 |
| Net debt | Baseline | 2027 Q3 | 30.7 | 33.5 | 44.2 |
| Net debt | Baseline | 2028 Q3 | 26.7 | 34.0 | 49.8 |
| Net debt | Baseline | 2031 Q3 | 15.5 | 35.4 | 62.0 |
| Net debt | With the decision | 2027 Q3 | 36.4 | 40.7 | 51.7 |
| Net debt | With the decision | 2028 Q3 | 32.7 | 41.1 | 57.2 |
| Net debt | With the decision | 2031 Q3 | 21.5 | 41.4 | 68.1 |

*Model values at the cutoff, USD bn*

| Value | Scenario | p10 | p50 | p90 | Undefined on |
|---|---|---|---|---|---|
| Enterprise value (DCF, model) | Baseline | 33.3 | 93.3 | 155.4 | 27.6% |
| Equity value (model) | Baseline | −2.8 | 57.2 | 119.3 | 27.6% |
| Enterprise value (DCF, model) | With the decision | 23.5 | 87.7 | 151.9 | 25.4% |
| Equity value (model) | With the decision | −12.6 | 51.6 | 115.8 | 25.4% |
| Paired change of enterprise value | With the decision | −6.6 | −3.9 | −0.2 | 27.6% |

*Share of paths with each event within the horizon*

| Event | Scenario | Share | Monte Carlo error | Upper 95% |
|---|---|---|---|---|
| Funding shortfall: cash and the revolver do not cover needs | Baseline | 34.3% | 0.9% | 36.1% |
| Covenant breach in any quarter | Baseline | 99.4% | 0.1% | 99.6% |
| Cash below its minimum in any quarter | Baseline | 38.7% | 0.9% | 40.4% |
| Negative operating FCFF over four quarters in a row | Baseline | 80.7% | 0.7% | 82.1% |
| Funding shortfall: cash and the revolver do not cover needs | With the decision | 37.1% | 0.9% | 38.9% |
| Covenant breach in any quarter | With the decision | 99.5% | 0.1% | 99.7% |
| Cash below its minimum in any quarter | With the decision | 42.2% | 0.9% | 43.9% |
| Negative operating FCFF over four quarters in a row | With the decision | 79.6% | 0.7% | 81.0% |


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
| As run | 1000 | −2.3 | 3.4 | 6.9 | −4.0 | 99.7% |
| Mean block of 2 quarters | 1000 | −1.8 | 3.3 | 6.9 | −4.0 | 99.7% |
| Mean block of 8 quarters | 1000 | −2.2 | 3.3 | 6.8 | −3.8 | 99.5% |
| All shocks 25% larger | 1000 | −2.9 | 3.5 | 8.4 | −3.8 | 99.6% |
| Macro columns locked | 1000 | −2.3 | 3.4 | 6.7 | −4.0 | 99.8% |


## 10. Limitations

Probabilities and quantiles are conditional on the assumed model: they are not calibrated and are not confidence intervals.

Enterprise and equity values come from a model DCF: they are model values, not market values, and no price per share is given.

Where the filings do not give an input, the case implies or assumes it, and the assumptions section lists each one.

Shocks are blocks of past quarters drawn again: a crisis unlike any of them is not in the paths.

Shocks met a hard bound in 0.0% of quarters. Enterprise value is undefined on 26.5% of paths: the values table counts them.

Value is undefined on 26.5% of paths.


## Claims

| Claim | Statement | Value | Unit | Pointer | Sources |
|---|---|---|---|---|---|
| C1 | Paths simulated | 3000 | paths | `/report/diagnostics/paths` | S7 |
| C2 | Seed of the run | 20261107 | count | `/report/manifest/settings/seed` | S7 |
| C3 | Knowledge cutoff | 2026-11-06 | date | `/case/as_of` | S1 |
| C4 | Opening balance date | 2026-09-30 | date | `/case/balance_date` | S1 |
| C5 | Quarters of shock history | 67 | quarters | `/report/diagnostics/history_quarters` | S1 |
| C6 | Firms behind the sector columns | 573 | count | `/case/shocks/peers` | S1 |
| C7 | Median model EV without the decision | 93329311232.22 | usd | `/report/values/0/p50` | S7 |
| C8 | Median model EV with the decision | 87669731404.03 | usd | `/report/values/2/p50` | S7 |
| C9 | p10 of the paired EV change | -6609109483.21 | usd | `/report/values/4/p10` | S7 |
| C10 | Median paired EV change | -3934496778.46 | usd | `/report/values/4/p50` | S7 |
| C11 | p90 of the paired EV change | -211627569.92 | usd | `/report/values/4/p90` | S7 |
| C12 | Share of paths with a covenant breach, with the decision | 0.995 | share | `/report/risks/5/probability` | S7 |

## Sources

- **S1** SEC EDGAR filings (XBRL company facts) (data_source): `/data-catalog/sec-edgar`
- **S2** U.S. Treasury par yield curve (data_source): `/data-catalog/us-treasury`
- **S3** World Bank GDP growth, CC BY 4.0 (data_source): `/data-catalog/world-bank`
- **S4** Source: ECB statistics (features of the model) (data_source): `/data-catalog/ecb-data-portal`
- **S5** Forecasting dataset (dataset): `fds-20261106-05c19bb5643a`
- **S6** Model of the central margin path (model): `live-20261106-95a7dc72f773`
- **S7** Paired Monte Carlo run (run): `sim-20261106-40dd0a976124`
- **S8** Financial statement engine, ADR-0029 (method): `docs/adr/0029-financial-engine.md`
- **S9** Paired Monte Carlo, ADR-0030 (method): `docs/adr/0030-paired-monte-carlo.md`
- **S10** Causal feasibility study, Stage 20 (method): `docs/stages/20-causal-research-pipeline.md`
- **S11** Report Studio, ADR-0034 (method): `docs/adr/0034-report-studio.md`
- **S12** SEC filing 0001628280-26-004357, 2024 Q4 (sec_filing): <https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/>
- **S13** SEC filing 0001628280-26-026458, 2025 Q1 (sec_filing): <https://www.sec.gov/Archives/edgar/data/12927/000162828026026458/>
- **S14** SEC filing 0001628280-26-050038, 2025 Q2 (sec_filing): <https://www.sec.gov/Archives/edgar/data/12927/000162828026050038/>
- **S15** SEC filing 0001628280-26-067508, 2025 Q3 (sec_filing): <https://www.sec.gov/Archives/edgar/data/12927/000162828026067508/>
