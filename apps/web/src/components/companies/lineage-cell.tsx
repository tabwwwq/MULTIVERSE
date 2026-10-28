import { X } from "lucide-react";
import { METHOD_LABELS } from "@/companies/labels";
import { formatAmount, unitLabel } from "@/companies/format";
import type { Scale } from "@/companies/params";
import { type DossierCell, dateOnly } from "@/companies/pit";
import { safeExternalUrl } from "@/lib/safe-url";

/*
 * A value with its lineage in a toggletip: a button opens a popover="auto" panel
 * (light dismiss and Esc built in). Click-to-open works on touch and keyboard,
 * unlike hover-only tooltips, and needs no JavaScript.
 */

interface LineageCellProps {
  id: string;
  cell: DossierCell | undefined;
  metricLabel: string;
  quarterLabel: string;
  currency: string;
  scale: Scale;
}

function display(cell: DossierCell, scale: Scale): string {
  if (cell.state === "not_public") return "Not public";
  if (cell.state === "missing" || cell.value.quantity === null) return "—";
  return formatAmount(cell.value.quantity.value, scale);
}

export function LineageCell({
  id,
  cell,
  metricLabel,
  quarterLabel,
  currency,
  scale,
}: LineageCellProps) {
  if (!cell) return <span className="text-ink-muted">—</span>;
  const shown = display(cell, scale);
  const spoken =
    cell.state === "value"
      ? `${shown} ${unitLabel(currency, scale)}`
      : cell.state === "missing"
        ? "Missing"
        : "Not public yet";
  // The accessible name starts with the visible text (WCAG 2.5.3 label in name).
  const accessibleName = `${spoken}, ${metricLabel}, ${quarterLabel}. Show lineage`;
  const { lineage } = cell.value;
  const document = safeExternalUrl(cell.filing?.url);

  return (
    <>
      <button
        type="button"
        popoverTarget={id}
        aria-label={accessibleName}
        className={
          cell.state === "value"
            ? "lineage-trigger text-ink"
            : "lineage-trigger text-ink-muted italic"
        }
      >
        {shown}
      </button>
      <div id={id} popover="auto" className="lineage-popover">
        <div className="mb-3 flex items-start justify-between gap-3">
          <p className="font-medium text-ink">
            {metricLabel}, {quarterLabel}
          </p>
          <button
            type="button"
            popoverTarget={id}
            popoverTargetAction="hide"
            aria-label="Close lineage"
            className="-m-1.5 rounded-control p-1.5 text-ink-muted hover:bg-inset hover:text-ink"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>
        <dl className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-3 gap-y-2 text-small">
          <dt className="text-ink-muted">Value</dt>
          <dd className="text-ink tabular-nums">{spoken}</dd>
          {cell.reason ? (
            <>
              <dt className="text-ink-muted">Why</dt>
              <dd className="text-ink">{cell.reason}</dd>
            </>
          ) : null}
          <dt className="text-ink-muted">Period end</dt>
          <dd className="text-ink tabular-nums">{cell.value.period.end_date}</dd>
          {lineage ? (
            <>
              <dt className="text-ink-muted">Source items</dt>
              <dd className="flex flex-col text-ink">
                {lineage.concepts.map((concept) => (
                  <code key={concept} className="text-micro break-all">
                    {concept}
                  </code>
                ))}
              </dd>
              <dt className="text-ink-muted">Method</dt>
              <dd className="text-ink">
                {METHOD_LABELS[lineage.method]}
                {lineage.formula ? `: ${lineage.formula}` : null}
              </dd>
            </>
          ) : null}
          {cell.filing ? (
            <>
              <dt className="text-ink-muted">Filing</dt>
              <dd className="text-ink tabular-nums">
                {cell.filing.form}, {cell.filing.accession_number}
              </dd>
              <dt className="text-ink-muted">Filed on</dt>
              <dd className="text-ink tabular-nums">{dateOnly(cell.filing.filed_at)}</dd>
              <dt className="text-ink-muted">Document</dt>
              <dd className="text-ink">
                {document ? (
                  <a href={document} rel="noopener noreferrer" className="text-blue underline">
                    Open the original filing
                  </a>
                ) : (
                  "None: this filing is synthetic"
                )}
              </dd>
            </>
          ) : null}
        </dl>
      </div>
    </>
  );
}
