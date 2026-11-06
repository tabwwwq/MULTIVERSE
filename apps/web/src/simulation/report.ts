import type { SimulationReport } from "@multiverse/contracts";

/** The report of a run on screen. Probabilities stay conditional on the assumed model. */

export const SCENARIO_LABELS = { baseline: "Baseline", alt_a: "With the decision" } as const;

export const VALUE_LABELS = {
  enterprise_value: "Enterprise value (DCF, model)",
  equity_value: "Equity value (model)",
  ev_change: "Paired change of EV",
} as const;

export const ORIGIN_LABELS = {
  observed: "Observed",
  implied: "Implied",
  assumed: "Assumed",
  model: "From the model",
} as const;

export const DRIVER_UNITS = {
  points_of_growth: "points",
  points_of_margin: "points",
  points_of_rate: "points",
  yes_no: "",
} as const;

export function percent(value: number, digits = 1): string {
  return `${(100 * value).toFixed(digits)}%`;
}

/** Zero on n paths is not zero risk: show the bound the run can support. */
export function probabilityText(row: SimulationReport["risks"][number]): string {
  if (row.probability === 0) return `None seen, below ${percent(row.upper_95, 2)}`;
  return `${percent(row.probability)} ± ${percent(2 * row.standard_error)}`;
}

export function originCounts(report: SimulationReport) {
  const counts = { observed: 0, implied: 0, assumed: 0, model: 0 };
  for (const input of report.inputs) counts[input.origin] += 1;
  return counts;
}

export function convergenceSizes(report: SimulationReport): number[] {
  return [...new Set(report.convergence.map((row) => row.paths))].sort((a, b) => a - b);
}

/** Share of the rows at a size that lie within two standard errors of the longest run. */
export function settledShare(report: SimulationReport, paths: number): number {
  const rows = report.convergence.filter((row) => row.paths === paths);
  return rows.filter((row) => row.within_two_errors).length / Math.max(rows.length, 1);
}

export function driverText(driver: SimulationReport["tails"][number]["drivers"][number]): string {
  if (driver.unit === "yes_no") return driver.value === 1 ? "Yes" : "No";
  const signed = driver.value > 0 ? `+${driver.value.toFixed(2)}` : driver.value.toFixed(2);
  return `${signed} ${DRIVER_UNITS[driver.unit]}`;
}
