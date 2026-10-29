import type { ScenarioRevision } from "@multiverse/contracts";
import { decisionRows } from "@/notebook/report";

/*
 * Comparing two saved revisions. Revisions with a different knowledge cutoff, horizon
 * or currency cannot be compared: no alignment method exists yet, and the prompt rules
 * out a comparison without one (FC-09). Comparable revisions show what differs.
 */

export interface RevisionDiff {
  label: string;
  left: string;
  right: string;
}

export interface RevisionComparison {
  compatible: boolean;
  reasons: string[];
  diffs: RevisionDiff[];
  same: number;
}

export function compareRevisions(
  left: ScenarioRevision,
  right: ScenarioRevision,
): RevisionComparison {
  const a = left.draft;
  const b = right.draft;
  const reasons: string[] = [];
  if (a.company_id !== b.company_id) reasons.push("The revisions are for different companies.");
  if (a.as_of !== b.as_of) reasons.push(`Different knowledge cutoffs (${a.as_of} and ${b.as_of}).`);
  if (a.horizon_quarters !== b.horizon_quarters) {
    reasons.push(`Different horizons (${a.horizon_quarters} and ${b.horizon_quarters} quarters).`);
  }
  if (left.currency !== right.currency) {
    reasons.push(`Different currencies (${left.currency} and ${right.currency}).`);
  }
  if (reasons.length > 0) return { compatible: false, reasons, diffs: [], same: 0 };

  const rowsA = new Map(decisionRows(left));
  const rowsB = new Map(decisionRows(right));
  rowsA.set("Seed", String(a.seed));
  rowsB.set("Seed", String(b.seed));
  rowsA.set("Sensitivity", a.sensitivity.parameters.join(", ") || "none");
  rowsB.set("Sensitivity", b.sensitivity.parameters.join(", ") || "none");
  const labels = [...new Set([...rowsA.keys(), ...rowsB.keys()])];
  const diffs: RevisionDiff[] = [];
  let same = 0;
  for (const label of labels) {
    const valueA = rowsA.get(label) ?? "—";
    const valueB = rowsB.get(label) ?? "—";
    if (valueA === valueB) same += 1;
    else diffs.push({ label, left: valueA, right: valueB });
  }
  return { compatible: true, reasons: [], diffs, same };
}
