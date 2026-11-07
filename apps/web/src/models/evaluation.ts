/*
 * Measured quality of the model without FRED (Stage 24b), copied from the stage report so the
 * page shows what was measured and nothing else:
 *   errors   benchmark bench-20261106-20302859cff2, test years 2020 to 2026, all firms, GRU;
 *   coverage evaluation eval-20261106-e0f63128e644, final years 2024 to 2026, test firms.
 * Source: docs/stages/24b-real-companies.md, sections "Measured results" and "Диапазоны".
 */

export interface ErrorRow {
  target: string;
  horizon: number;
  /** MAE of the model against persistence, in percent: negative is better. */
  change: number;
  low: number;
  high: number;
}

export const BENCHMARK_ID = "bench-20261106-20302859cff2";
export const EVALUATION_ID = "eval-20261106-e0f63128e644";

export const ERRORS: readonly ErrorRow[] = [
  { target: "Revenue growth", horizon: 1, change: -4.6, low: -7.0, high: -2.1 },
  { target: "Revenue growth", horizon: 4, change: -31.7, low: -33.4, high: -29.9 },
  { target: "Revenue growth", horizon: 8, change: -39.7, low: -42.2, high: -37.2 },
  { target: "Operating margin", horizon: 1, change: -22.3, low: -51.7, high: -0.4 },
  { target: "Operating margin", horizon: 4, change: -34.1, low: -66.4, high: -1.2 },
  { target: "Operating margin", horizon: 8, change: -50.5, low: -74.7, high: -16.2 },
  { target: "EBITDA margin", horizon: 1, change: -24.3, low: -63.4, high: 10.5 },
  { target: "EBITDA margin", horizon: 4, change: -27.4, low: -67.5, high: 4.5 },
  { target: "EBITDA margin", horizon: 8, change: -46.8, low: -76.0, high: -8.6 },
  { target: "FCF margin", horizon: 1, change: -38.2, low: -70.7, high: -6.7 },
  { target: "FCF margin", horizon: 4, change: -51.0, low: -78.3, high: -19.6 },
  { target: "FCF margin", horizon: 8, change: -45.6, low: -78.0, high: -9.7 },
  { target: "Debt / EBITDA", horizon: 1, change: -45.5, low: -48.7, high: -22.5 },
  { target: "Debt / EBITDA", horizon: 4, change: -47.2, low: -50.1, high: -30.5 },
  { target: "Debt / EBITDA", horizon: 8, change: -44.5, low: -55.3, high: -31.3 },
];

export interface CoverageRow {
  label: string;
  /** Share of outcomes inside the p10 to p90 band, in percent. */
  held: number;
  rows: number;
  approved: boolean;
}

export const NOMINAL = 80;

export const COVERAGE: readonly CoverageRow[] = [
  { label: "Revenue growth, 4 quarters", held: 82.2, rows: 4394, approved: true },
  { label: "Revenue growth, 8 quarters", held: 80.4, rows: 1674, approved: true },
  { label: "Operating margin, 4 quarters", held: 82.4, rows: 3742, approved: false },
  { label: "FCF margin, 4 quarters", held: 81.8, rows: 3613, approved: false },
  { label: "EBITDA margin, 4 quarters", held: 85.2, rows: 3484, approved: false },
  { label: "Debt / EBITDA, 4 quarters", held: 86.5, rows: 2062, approved: false },
];
