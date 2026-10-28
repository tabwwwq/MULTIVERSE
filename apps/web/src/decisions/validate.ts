import type { ScenarioDraft } from "@multiverse/contracts";
import type { CompanyContext, CutoffFacts } from "@/decisions/context";
import { eligibilityIssues } from "@/decisions/eligibility";
import { readScenarioForm, type ScenarioForm, toScenarioDraft } from "@/decisions/form";
import { resolveDecision, type ResolvedLine } from "@/decisions/resolve";
import { checkRules, type Issue, planningWarnings } from "@/decisions/rules";

/*
 * Validate = read the form, apply the contract rules, check eligibility for the company
 * at the cutoff, then translate the decision into dollars (PRD FR-DE, US-03 to US-05).
 * The result remembers the cutoff and the inputs it was computed for, so it can be
 * marked stale when either changes (PRD FR-TM-03).
 */

export interface ValidationResult {
  asOf: string;
  fingerprint: string;
  issues: Issue[];
  errors: number;
  warnings: number;
  /** The contract draft when there are no blocking errors. */
  draft: ScenarioDraft | null;
  resolved: ResolvedLine[];
}

export type Freshness =
  { state: "fresh" } | { state: "stale_as_of"; from: string; to: string } | { state: "changed" };

/** Everything a result depends on except the cutoff, which is compared on its own. */
export function fingerprint(form: ScenarioForm): string {
  return JSON.stringify({ ...form, as_of: null });
}

export function freshness(result: ValidationResult, form: ScenarioForm): Freshness {
  if (result.asOf !== form.as_of)
    return { state: "stale_as_of", from: result.asOf, to: form.as_of };
  if (result.fingerprint !== fingerprint(form)) return { state: "changed" };
  return { state: "fresh" };
}

/** One issue per field: what the form could not read hides rules about the same field. */
function merge(first: Issue[], second: Issue[]): Issue[] {
  const seen = new Set(first.map((issue) => issue.path));
  return [
    ...first,
    ...second.filter((issue) => !seen.has(issue.path) || issue.severity === "warning"),
  ];
}

export function factsFor(context: CompanyContext, asOf: string): CutoffFacts | undefined {
  return context.cutoffs.find((facts) => facts.asOf === asOf);
}

export function validateScenario(form: ScenarioForm, context: CompanyContext): ValidationResult {
  const read = readScenarioForm(form);
  const facts = factsFor(context, form.as_of);
  const rules = merge(read.issues, checkRules(read.draft));
  const issues = merge(rules, [
    ...eligibilityIssues(read.draft, context, facts),
    ...planningWarnings(read.draft),
  ]);
  const errors = issues.filter((issue) => issue.severity === "error").length;
  const draft = errors === 0 ? toScenarioDraft(form, read) : null;
  return {
    asOf: form.as_of,
    fingerprint: fingerprint(form),
    issues,
    errors,
    warnings: issues.length - errors,
    draft,
    resolved: draft && facts ? resolveDecision(draft, facts) : [],
  };
}
