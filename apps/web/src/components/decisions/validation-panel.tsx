"use client";

import { CircleAlert, TriangleAlert } from "lucide-react";
import type { RefObject } from "react";
import { Alert } from "@/components/ui/alert";
import { fieldId, focusField } from "@/decisions/fields";
import type { Issue } from "@/decisions/rules";
import type { Freshness, ValidationResult } from "@/decisions/validate";

function IssueList({ issues, title }: { issues: Issue[]; title: string }) {
  if (issues.length === 0) return null;
  const isError = issues[0]?.severity === "error";
  const Icon = isError ? CircleAlert : TriangleAlert;
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-small font-medium text-ink">{title}</h3>
      <ul className="flex flex-col gap-2">
        {issues.map((issue, index) => (
          <li
            key={`${issue.path}-${issue.code}-${index}`}
            className="flex items-start gap-2 text-small"
          >
            <Icon
              aria-hidden="true"
              className={`mt-0.5 size-4 shrink-0 ${isError ? "text-negative" : "text-warning"}`}
            />
            <a
              href={`#${fieldId(issue.path)}`}
              onClick={(event) => {
                event.preventDefault();
                focusField(issue.path);
              }}
              className="rounded-control text-ink underline decoration-line-strong underline-offset-4 hover:decoration-mint"
            >
              {issue.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface ValidationPanelProps {
  result: ValidationResult | null;
  freshness: Freshness | null;
  headingRef: RefObject<HTMLHeadingElement | null>;
}

/** Errors and warnings with links to their fields, then the decision in dollars. */
export function ValidationPanel({ result, freshness, headingRef }: ValidationPanelProps) {
  const errors = result?.issues.filter((issue) => issue.severity === "error") ?? [];
  const warnings = result?.issues.filter((issue) => issue.severity === "warning") ?? [];
  const fresh = freshness?.state === "fresh";

  return (
    <section aria-labelledby="validation-title" className="flex flex-col gap-4">
      <h2
        id="validation-title"
        ref={headingRef}
        tabIndex={-1}
        className="font-display text-h3 text-ink focus:outline-none"
      >
        Validation
      </h2>

      {!result ? (
        <p className="text-body text-ink-muted">
          Not validated yet. Validate to check every rule and see the decision in dollars at the
          cutoff.
        </p>
      ) : null}

      {freshness?.state === "stale_as_of" ? (
        <Alert tone="warning" title="Stale — requires rerun" live>
          The knowledge cutoff changed from {freshness.from} to {freshness.to} after validation. The
          figures below were computed with what was public on {freshness.from}. Validate again.
        </Alert>
      ) : null}
      {freshness?.state === "changed" ? (
        <Alert tone="info" title="Changed since validation" live>
          Inputs changed after the last check. Validate again before a run.
        </Alert>
      ) : null}

      {result ? (
        <div className={fresh ? "flex flex-col gap-4" : "flex flex-col gap-4 opacity-70"}>
          <p className="text-body text-ink" data-testid="validation-status">
            {result.errors > 0
              ? `${result.errors} ${result.errors === 1 ? "error blocks" : "errors block"} a run`
              : "No blocking errors"}
            {result.warnings > 0
              ? `, ${result.warnings} ${result.warnings === 1 ? "warning" : "warnings"}.`
              : "."}{" "}
            <span className="text-ink-muted">Checked for the cutoff {result.asOf}.</span>
          </p>
          <IssueList issues={errors} title="Errors" />
          <IssueList issues={warnings} title="Warnings" />
          {result.resolved.length > 0 ? (
            <div className="flex flex-col gap-2">
              <h3 className="text-small font-medium text-ink">
                The decision in dollars, with what was public on {result.asOf}
              </h3>
              <dl className="flex flex-col divide-y divide-line rounded-panel border border-line bg-surface">
                {result.resolved.map((line) => (
                  <div
                    key={line.label}
                    className="grid gap-1 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto]"
                  >
                    <dt className="text-small text-ink">{line.label}</dt>
                    <dd className="text-body font-medium text-ink tabular-nums sm:text-right">
                      {line.value}
                    </dd>
                    <dd className="text-small text-ink-muted sm:col-span-2">{line.basis}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-small text-ink-muted">
                Arithmetic on point-in-time figures, not a forecast. Ranges use their central value.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
