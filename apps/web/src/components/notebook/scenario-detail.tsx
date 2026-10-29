"use client";

import type { ScenarioRecord, ScenarioRevision } from "@multiverse/contracts";
import { Copy, Download, FileText, Lock, PencilLine } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { CONTROL, SelectField, TextField } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { formatMagnitude, specFor, unitSpecFor } from "@/decisions/catalog";
import { cn } from "@/lib/cn";
import { downloadText } from "@/lib/download";
import { compareRevisions } from "@/notebook/compare";
import {
  type CompanyNames,
  metaIssues,
  type Notebook,
  parseTags,
  reportsFor,
  type ScenarioMeta,
} from "@/notebook/model";

export function decisionSummary(revision: ScenarioRevision): string {
  const { decision } = revision.draft;
  const spec = specFor(decision.type);
  const unit = unitSpecFor(spec, decision.magnitude.unit);
  return `${spec.label}: ${unit ? formatMagnitude(decision.magnitude.value, unit) : decision.magnitude.value}, cutoff ${revision.draft.as_of}`;
}

function shortTime(iso: string): string {
  return iso.replace("T", " ").slice(0, 16);
}

interface ScenarioDetailProps {
  record: ScenarioRecord;
  notebook: Notebook;
  companies: CompanyNames;
  onSaveMeta: (meta: ScenarioMeta) => void;
  onDuplicate: (revision: number) => void;
  onExport: (revision: number) => void;
  onDelete: () => void;
}

export function ScenarioDetail({
  record,
  notebook,
  companies,
  onSaveMeta,
  onDuplicate,
  onExport,
  onDelete,
}: ScenarioDetailProps) {
  const [name, setName] = useState(record.name);
  const [tags, setTags] = useState(record.tags.join(", "));
  const [notes, setNotes] = useState(record.notes);
  const [metaErrors, setMetaErrors] = useState<string[]>([]);
  const allRevisions = notebook.scenarios.flatMap((item) =>
    item.revisions.map((revision) => ({
      record: item,
      revision,
      key: `${item.scenario_id}:${revision.revision}`,
    })),
  );
  const own = allRevisions.filter((item) => item.record.scenario_id === record.scenario_id);
  const [left, setLeft] = useState(own.at(-2)?.key ?? own[0]?.key ?? "");
  const [right, setRight] = useState(own.at(-1)?.key ?? "");
  const company = companies[record.revisions[0]?.draft.company_id ?? ""];
  const scenarioReports = notebook.reports.filter(
    (report) => report.source.scenario_id === record.scenario_id,
  );
  const leftItem = allRevisions.find((item) => item.key === left);
  const rightItem = allRevisions.find((item) => item.key === right);
  const comparison =
    leftItem && rightItem && left !== right
      ? compareRevisions(leftItem.revision, rightItem.revision)
      : null;

  return (
    <article aria-labelledby="scenario-title" className="flex min-w-0 flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h2 id="scenario-title" className="font-display text-h3 text-ink">
          {record.name}
        </h2>
        <p className="text-small text-ink-muted">
          {company?.name ?? "Unknown company"}
          {company?.ticker ? ` (${company.ticker})` : ""} · {record.revisions.length}{" "}
          {record.revisions.length === 1 ? "revision" : "revisions"} · updated{" "}
          {shortTime(record.updated_at)}
        </p>
      </header>

      <section aria-labelledby="meta-title" className="flex flex-col gap-4">
        <h3 id="meta-title" className="font-display text-h4 text-ink">
          Name, tags and notes
        </h3>
        <p className="text-small text-ink-muted">
          These describe the scenario. Changing them creates no revision.
        </p>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            const meta = { name, tags: parseTags(tags), notes };
            const issues = metaIssues(meta);
            setMetaErrors(issues);
            if (issues.length === 0) onSaveMeta(meta);
          }}
        >
          <TextField
            id="meta-name"
            label="Name"
            required
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <TextField
            id="meta-tags"
            label="Tags"
            hint="Separated by commas."
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="meta-notes" className="text-small font-medium text-ink">
              Notes
            </label>
            <textarea
              id="meta-notes"
              rows={3}
              maxLength={5000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={cn(CONTROL, "py-2")}
            />
          </div>
          {metaErrors.length > 0 ? (
            <ul role="alert" className="text-small text-negative">
              {metaErrors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          ) : null}
          <div>
            <Button type="submit" variant="secondary" size="sm">
              <PencilLine aria-hidden="true" />
              Save details
            </Button>
          </div>
        </form>
      </section>

      <section aria-labelledby="revisions-title" className="flex flex-col gap-4">
        <h3 id="revisions-title" className="font-display text-h4 text-ink">
          Revisions
        </h3>
        <p className="text-small text-ink-muted">
          A revision never changes. Opening one in the Decision Builder and saving creates the next
          revision.
        </p>
        <ol className="flex flex-col gap-3">
          {[...record.revisions].reverse().map((revision) => {
            const reports = reportsFor(notebook, {
              scenario_id: record.scenario_id,
              revision: revision.revision,
            });
            const restore = `/decisions?company=${revision.draft.company_id}&restore=${record.scenario_id}&revision=${revision.revision}`;
            return (
              <li
                key={revision.revision}
                className="flex flex-col gap-3 rounded-panel border border-line bg-surface p-4"
                data-testid={`revision-${revision.revision}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-ink">Revision {revision.revision}</p>
                  <div className="flex flex-wrap gap-2">
                    <Badge>Not run</Badge>
                    {revision.exported ? (
                      <Badge tone="blue" icon={Lock}>
                        Report exported
                      </Badge>
                    ) : null}
                  </div>
                </div>
                <p className="text-small text-ink">{decisionSummary(revision)}</p>
                <p className="text-micro text-ink-muted">
                  Saved {shortTime(revision.created_at)}
                  {revision.parent_revision
                    ? ` · edited from revision ${revision.parent_revision}`
                    : ""}
                  {revision.derived_from
                    ? ` · duplicated from another scenario (revision ${revision.derived_from.revision})`
                    : ""}
                  {reports.length > 0
                    ? ` · ${reports.length} ${reports.length === 1 ? "report" : "reports"}`
                    : ""}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Link
                    href={restore}
                    className={buttonClasses({ variant: "secondary", size: "sm" })}
                  >
                    Open in Decision Builder
                  </Link>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onDuplicate(revision.revision)}
                  >
                    <Copy aria-hidden="true" />
                    Duplicate as new scenario
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => onExport(revision.revision)}>
                    <FileText aria-hidden="true" />
                    Export report
                  </Button>
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-labelledby="compare-title" className="flex flex-col gap-4">
        <h3 id="compare-title" className="font-display text-h4 text-ink">
          Compare two revisions
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {[
            { id: "compare-left", label: "First revision", value: left, set: setLeft },
            { id: "compare-right", label: "Second revision", value: right, set: setRight },
          ].map((field) => (
            <SelectField
              key={field.id}
              id={field.id}
              label={field.label}
              value={field.value}
              onChange={(event) => field.set(event.target.value)}
            >
              {allRevisions.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.record.name} · revision {item.revision.revision}
                </option>
              ))}
            </SelectField>
          ))}
        </div>
        {left === right ? (
          <p className="text-small text-ink-muted">Choose two different revisions.</p>
        ) : null}
        {comparison && !comparison.compatible ? (
          <Alert tone="negative" title="Comparison blocked">
            <ul className="list-disc pl-5">
              {comparison.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <p className="mt-2">
              No method exists yet to align such revisions, so they are not compared.
            </p>
          </Alert>
        ) : null}
        {comparison?.compatible ? (
          comparison.diffs.length === 0 ? (
            <p className="text-small text-ink-muted">
              The two revisions are the same in every parameter.
            </p>
          ) : (
            <div
              role="region"
              aria-labelledby="diff-caption"
              tabIndex={0}
              className="data-table rounded-panel border border-line bg-surface"
            >
              <table>
                <caption id="diff-caption">
                  {comparison.diffs.length} differences, {comparison.same} parameters the same
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Parameter</th>
                    <th scope="col">
                      {leftItem ? `Revision ${leftItem.revision.revision}` : "First"}
                    </th>
                    <th scope="col">
                      {rightItem ? `Revision ${rightItem.revision.revision}` : "Second"}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.diffs.map((diff) => (
                    <tr key={diff.label}>
                      <th scope="row">{diff.label}</th>
                      <td
                        data-label={leftItem ? `Revision ${leftItem.revision.revision}` : "First"}
                      >
                        {diff.left}
                      </td>
                      <td
                        data-label={
                          rightItem ? `Revision ${rightItem.revision.revision}` : "Second"
                        }
                      >
                        {diff.right}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : null}
      </section>

      <section aria-labelledby="reports-title" className="flex flex-col gap-4">
        <h3 id="reports-title" className="font-display text-h4 text-ink">
          Exported reports
        </h3>
        {scenarioReports.length === 0 ? (
          <p className="text-small text-ink-muted">
            None yet. Each export is kept as it was; a new export never replaces an earlier one.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-line rounded-panel border border-line bg-surface">
            {scenarioReports.map((report) => (
              <li
                key={report.report_id}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
                data-testid="report-row"
              >
                <span className="flex flex-col">
                  <span className="text-small text-ink">
                    Revision {report.source.revision} · exported {shortTime(report.created_at)}
                  </span>
                  <span className="text-micro text-ink-muted tabular-nums">
                    Report {report.report_id.slice(0, 8)} · SHA-256{" "}
                    {report.content_sha256.slice(0, 12)}
                  </span>
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    downloadText(report.file_name, report.content, "text/markdown;charset=utf-8")
                  }
                >
                  <Download aria-hidden="true" />
                  Download again
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section
        aria-labelledby="delete-title"
        className="flex flex-col gap-3 border-t border-line pt-6"
      >
        <h3 id="delete-title" className="text-small font-medium text-ink">
          Delete this scenario
        </h3>
        {scenarioReports.length > 0 ? (
          <p className="text-small text-ink-muted">
            A scenario with exported reports cannot be deleted: the reports point at its revisions.
          </p>
        ) : (
          <div>
            <Modal
              title={`Delete “${record.name}”?`}
              description="All its revisions are removed from this device. This cannot be undone."
              triggerLabel="Delete scenario"
              triggerVariant="danger"
              cancelLabel="Keep it"
              confirmLabel="Delete"
              onClose={(result) => {
                if (result === "confirm") onDelete();
              }}
            />
          </div>
        )}
      </section>
    </article>
  );
}
