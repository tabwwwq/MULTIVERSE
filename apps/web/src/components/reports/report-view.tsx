import type { ReportTable, ResearchReport } from "@multiverse/contracts";
import { Download, ExternalLink, Printer } from "lucide-react";
import Link from "next/link";
import { Fragment } from "react";
import { Alert } from "@/components/ui/alert";
import { buttonClasses } from "@/components/ui/button";
import { reportFileUrl } from "@/models/jobs";
import { downloadName, segments, sourceLink } from "@/reports/view";

interface ReportViewProps {
  report: ResearchReport;
  jobId: string;
  onPrint: () => void;
}

function Paragraph({ text }: { text: string }) {
  return (
    <p className="max-w-prose text-body text-ink">
      {segments(text).map((part, index) => {
        if (part.kind === "text") return <Fragment key={index}>{part.text}</Fragment>;
        const href = part.kind === "claim" ? `#claim-${part.id}` : `#source-${part.id}`;
        return (
          <a
            key={index}
            href={href}
            className="font-mono text-small text-mint underline underline-offset-2"
            aria-label={part.kind === "claim" ? `Claim ${part.id}` : `Source ${part.id}`}
          >
            {part.kind === "claim" ? `[${part.id}]` : part.id}
          </a>
        );
      })}
    </p>
  );
}

function Table({ table, id }: { table: ReportTable; id: string }) {
  return (
    <div className="report-table overflow-x-auto rounded-control border border-line" tabIndex={0}>
      <table className="w-full border-collapse text-small" aria-describedby={`${id}-caption`}>
        <caption id={`${id}-caption`} className="px-3 py-2 text-left text-ink-muted">
          {table.caption}
          {table.unit_note ? `, ${table.unit_note}` : ""}
        </caption>
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th
                key={column}
                scope="col"
                className="border-t border-line bg-inset px-3 py-2 text-left font-medium text-ink"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) =>
                c === 0 ? (
                  <th
                    key={c}
                    scope="row"
                    className="border-t border-line px-3 py-2 text-left font-normal text-ink"
                  >
                    {cell}
                  </th>
                ) : (
                  <td key={c} className="border-t border-line px-3 py-2 text-ink tabular-nums">
                    {/^S\d{1,3}$/.test(cell) ? (
                      <a href={`#source-${cell}`} className="text-mint underline">
                        {cell}
                      </a>
                    ) : (
                      cell
                    )}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One research report, readable on screen and on paper, every number traceable to the run. */
export function ReportView({ report, jobId, onPrint }: ReportViewProps) {
  const download = (part: "markdown" | "csv" | "manifest", label: string) => (
    <a
      href={reportFileUrl(jobId, part)}
      download={downloadName(report, part)}
      className={buttonClasses({ variant: "secondary", size: "sm" })}
    >
      <Download aria-hidden="true" />
      {label}
    </a>
  );
  return (
    <article className="report flex flex-col gap-10" aria-labelledby="report-title">
      <header className="flex flex-col gap-4 border-b border-line pb-6">
        <p className="text-small font-medium tracking-wide text-mint uppercase">
          MULTIVERSE · Report Studio
        </p>
        <h2 id="report-title" className="font-display text-h3 text-ink">
          {report.title}
        </h2>
        <Alert tone="warning" title={report.label}>
          Evidence level: {report.evidence_level.replaceAll("_", " ")}. Every number below links to
          the claim that says where it comes from in the run.
        </Alert>
        <dl className="grid gap-x-6 gap-y-1 text-small text-ink-muted sm:grid-cols-2">
          <div>
            <dt className="inline">Report </dt>
            <dd className="inline font-mono text-ink">{report.report_doc_id}</dd>
          </div>
          <div>
            <dt className="inline">Run </dt>
            <dd className="inline font-mono text-ink">{report.simulation_report_id}</dd>
          </div>
          <div>
            <dt className="inline">Generator </dt>
            <dd className="inline font-mono text-ink">{report.generator_version}</dd>
          </div>
          <div>
            <dt className="inline">Contracts </dt>
            <dd className="inline font-mono text-ink">{report.contracts_version}</dd>
          </div>
        </dl>
        <div className="print-hidden flex flex-wrap gap-3">
          {download("markdown", "Markdown")}
          {download("csv", "CSV")}
          {download("manifest", "Manifest")}
          <button
            type="button"
            onClick={onPrint}
            className={buttonClasses({ variant: "secondary", size: "sm" })}
          >
            <Printer aria-hidden="true" />
            Print or save as PDF
          </button>
        </div>
      </header>

      {report.sections.map((section, s) => (
        <section
          key={section.key}
          aria-labelledby={`section-${section.key}`}
          className="flex flex-col gap-4"
        >
          <h3 id={`section-${section.key}`} className="font-display text-h4 text-ink">
            {s + 1}. {section.title}
          </h3>
          {section.paragraphs.map((text, p) => (
            <Paragraph key={p} text={text} />
          ))}
          {section.tables.map((table, t) => (
            <Table key={t} table={table} id={`${section.key}-${t}`} />
          ))}
        </section>
      ))}

      <section aria-labelledby="section-claims" className="flex flex-col gap-4">
        <h3 id="section-claims" className="font-display text-h4 text-ink">
          Claims
        </h3>
        <p className="max-w-prose text-body text-ink-muted">
          Each claim gives the value as stored in the run and a JSON pointer into it, so a reader
          can check it without trusting this page.
        </p>
        <ol className="flex flex-col gap-2">
          {report.claims.map((claim) => (
            <li
              key={claim.claim_id}
              id={`claim-${claim.claim_id}`}
              className="scroll-mt-24 rounded-control border border-line p-3 text-small"
            >
              <span className="font-mono text-mint">{claim.claim_id}</span> {claim.statement}:{" "}
              <span className="font-mono text-ink">{claim.value}</span> ({claim.unit}), at{" "}
              <code className="break-all">{claim.pointer}</code>, sources {claim.sources.join(", ")}
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="section-sources" className="flex flex-col gap-4">
        <h3 id="section-sources" className="font-display text-h4 text-ink">
          Sources
        </h3>
        <ol className="flex flex-col gap-2">
          {report.sources.map((ref) => {
            const link = sourceLink(ref);
            return (
              <li
                key={ref.ref_id}
                id={`source-${ref.ref_id}`}
                className="scroll-mt-24 text-small text-ink"
              >
                <span className="font-mono text-mint">{ref.ref_id}</span> {ref.label}:{" "}
                {link.kind === "external" ? (
                  <a
                    href={link.href}
                    rel="noreferrer noopener"
                    target="_blank"
                    className="break-all text-mint underline"
                  >
                    {ref.target}
                    <ExternalLink aria-hidden="true" className="ml-1 inline size-3" />
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                ) : link.kind === "internal" ? (
                  <Link href={link.href} className="text-mint underline">
                    {ref.target}
                  </Link>
                ) : (
                  <code className="break-all">{ref.target}</code>
                )}
              </li>
            );
          })}
        </ol>
      </section>
    </article>
  );
}
