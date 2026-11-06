import type { TreatmentStudy } from "@multiverse/contracts/causal";

/** The feasibility study on screen (Stage 20): it reports what could be claimed, not effects. */

export const METHOD_LABELS: Record<TreatmentStudy["verdicts"][number]["method"], string> = {
  matched_cohort: "Matched cohort",
  weighted_regression: "Weighted regression",
  did_event_study: "Difference-in-differences and event study",
  synthetic_control: "Synthetic control",
};

/** Where each node of the graph sits in the drawing. */
export const POSITIONS: Record<string, { x: number; y: number }> = {
  macro: { x: 100, y: 45 },
  firm_state: { x: 100, y: 170 },
  expectations: { x: 380, y: 45 },
  other_decisions: { x: 100, y: 295 },
  action: { x: 330, y: 170 },
  costs: { x: 500, y: 125 },
  demand: { x: 500, y: 225 },
  outcome: { x: 665, y: 170 },
};

export function feasibleCount(row: TreatmentStudy): number {
  return row.verdicts.filter((verdict) => verdict.feasible).length;
}

export function growthRow(row: TreatmentStudy) {
  return (row.null ?? []).find((item) => item.outcome === "rev_growth_l1");
}
