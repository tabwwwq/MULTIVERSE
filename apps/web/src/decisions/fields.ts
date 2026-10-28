import type { Issue } from "@/decisions/rules";

/*
 * Contract paths name form fields: "decision.financing.debt" is the input with id
 * "f-financing-debt". Issues are shown at their field and linked from the summary.
 */

export function fieldId(path: string): string {
  const local = path
    .replace(/^decision\./, "")
    .replaceAll(".", "-")
    .replaceAll("_", "-");
  return `f-${local || "scenario"}`;
}

export interface FieldIssues {
  error?: string;
  warning?: string;
}

export function issuesByPath(issues: readonly Issue[]): Map<string, FieldIssues> {
  const byPath = new Map<string, FieldIssues>();
  for (const issue of issues) {
    const entry = byPath.get(issue.path) ?? {};
    if (issue.severity === "error") entry.error ??= issue.message;
    else entry.warning ??= issue.message;
    byPath.set(issue.path, entry);
  }
  return byPath;
}

/** Move focus to the control behind a path: the field itself, or the first control in a group. */
export function focusField(path: string): void {
  const target = document.getElementById(fieldId(path));
  if (!target) return;
  const control = target.matches("input, select, textarea, button")
    ? target
    : target.querySelector<HTMLElement>("input, select, textarea, button");
  (control ?? target).focus();
}
