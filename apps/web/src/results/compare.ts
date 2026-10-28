import type { ScenarioResult } from "@multiverse/contracts";

/*
 * Two results can be compared only on the same footing (PRD FR-RE-06, FC-09): the same
 * company, knowledge cutoff, currency and horizon. Otherwise the comparison is blocked
 * and the reasons are listed; nothing is realigned silently.
 */

export interface Compatibility {
  compatible: boolean;
  reasons: string[];
  /** Same seed too: the baselines coincide path by path. */
  pairedBaselines: boolean;
}

export function compatibility(a: ScenarioResult, b: ScenarioResult): Compatibility {
  const reasons: string[] = [];
  if (a.status !== "completed" || b.status !== "completed") {
    reasons.push("Only completed results can be compared.");
  }
  if (a.company_id !== b.company_id) {
    reasons.push(`The results are for different companies (${a.company_name}, ${b.company_name}).`);
  }
  if (a.as_of !== b.as_of) {
    reasons.push(`The results have different knowledge cutoffs (${a.as_of} and ${b.as_of}).`);
  }
  if (a.currency !== b.currency) {
    reasons.push(`The results use different currencies (${a.currency} and ${b.currency}).`);
  }
  if (a.horizon_quarters !== b.horizon_quarters) {
    reasons.push(
      `The results cover different horizons (${a.horizon_quarters} and ${b.horizon_quarters} quarters).`,
    );
  }
  const compatible = reasons.length === 0;
  return {
    compatible,
    reasons,
    pairedBaselines: compatible && a.seed === b.seed && a.paths === b.paths,
  };
}
