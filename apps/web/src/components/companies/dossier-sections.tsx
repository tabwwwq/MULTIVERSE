import type { Company, CompanyDossier, FilingReference } from "@multiverse/contracts";
import Form from "next/form";
import Link from "next/link";
import { ACCOUNTING_LABELS, DOSSIER_METRICS, SECTOR_LABELS, countryName } from "@/companies/labels";
import { unitLabel } from "@/companies/format";
import type { Scale } from "@/companies/params";
import { type DossierView, type QuarterRow, cutoffChoices, dateOnly } from "@/companies/pit";
import { CoverageMeter } from "@/components/companies/coverage-meter";
import { LineageCell } from "@/components/companies/lineage-cell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { SelectField } from "@/components/ui/field";
import { cn } from "@/lib/cn";
import { safeExternalUrl } from "@/lib/safe-url";

/** Building blocks of the company dossier page (PRD FR-CO-03, FR-CO-04, FR-TM-01, FR-TM-02). */

export function IdentityList({ company }: { company: Company }) {
  const items: Array<[string, React.ReactNode]> = [
    [
      "Company ID",
      <code key="id" className="text-micro break-all">
        {company.company_id}
      </code>,
    ],
    ["CIK", company.cik ?? "None"],
    ["Sector", SECTOR_LABELS[company.sector]],
    ["Country", countryName(company.country)],
    ["Reporting currency", company.reporting_currency],
    ["Accounting standard", ACCOUNTING_LABELS[company.accounting_standard]],
    ["Fiscal year end", `${company.fiscal_year_end} (month-day)`],
    ["Fiscal calendar", company.fiscal_52_53_week ? "52/53-week" : "Calendar months"],
  ];
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map(([term, detail]) => (
        <div key={term} className="flex flex-col gap-0.5">
          <dt className="text-micro text-ink-muted">{term}</dt>
          <dd className="text-small text-ink tabular-nums">{detail}</dd>
        </div>
      ))}
    </dl>
  );
}

function period(from: string, to: string | null | undefined): string {
  return to ? `${from} to ${to}` : `since ${from}`;
}

export function ListingHistory({ company }: { company: Company }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div>
        <h3 className="mb-2 font-medium text-ink">Tickers</h3>
        <ol className="flex flex-col gap-1.5 text-small">
          {company.listings.map((listing) => (
            <li
              key={`${listing.ticker}-${listing.valid_from}`}
              className="text-ink-muted tabular-nums"
            >
              <span className="font-medium text-ink">{listing.ticker}</span> on {listing.exchange},{" "}
              {period(listing.valid_from, listing.valid_to)}
            </li>
          ))}
        </ol>
      </div>
      <div>
        <h3 className="mb-2 font-medium text-ink">Legal names</h3>
        <ol className="flex flex-col gap-1.5 text-small">
          {company.names.map((name) => (
            <li key={`${name.name}-${name.valid_from}`} className="text-ink-muted tabular-nums">
              <span className="font-medium text-ink">{name.name}</span>,{" "}
              {period(name.valid_from, name.valid_to)}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

interface ControlsProps {
  companyId: string;
  dossier: CompanyDossier;
  asOf: string | null;
  scale: Scale;
}

export function DossierControls({ companyId, dossier, asOf, scale }: ControlsProps) {
  const base = `/dossier/${companyId}`;
  const scaleHref = (next: Scale) => {
    const params = new URLSearchParams();
    if (asOf) params.set("asOf", asOf);
    if (next !== "m") params.set("scale", next);
    const search = params.toString();
    return search ? `${base}?${search}` : base;
  };
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <Form action={base} scroll={false} className="flex flex-wrap items-end gap-3">
        <div className="min-w-56">
          <SelectField id="dossier-as-of" name="asOf" label="Known as of" defaultValue={asOf ?? ""}>
            <option value="">Latest snapshot ({dateOnly(dossier.as_of)})</option>
            {cutoffChoices(dossier).map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </SelectField>
        </div>
        {scale !== "m" ? <input type="hidden" name="scale" value={scale} /> : null}
        <Button type="submit" variant="secondary">
          Show
        </Button>
      </Form>
      <nav aria-label="Amount scale" className="flex gap-1 rounded-control border border-line p-1">
        {(["m", "bn"] as const).map((option) => (
          <Link
            key={option}
            href={scaleHref(option)}
            scroll={false}
            aria-current={scale === option ? "true" : undefined}
            className={cn(
              "flex min-h-10 items-center rounded-control px-3 text-small",
              scale === option ? "bg-inset text-ink" : "text-ink-muted hover:text-ink",
            )}
          >
            {unitLabel(dossier.company.reporting_currency, option)}
          </Link>
        ))}
      </nav>
    </div>
  );
}

export function FinancialTable({
  dossier,
  view,
  scale,
}: {
  dossier: CompanyDossier;
  view: DossierView;
  scale: Scale;
}) {
  const currency = dossier.company.reporting_currency;
  return (
    <DataTable<QuarterRow>
      id="financials"
      caption={`Quarterly results in ${unitLabel(currency, scale)}, as known on ${view.cutoff}. Select a value to see where it comes from.`}
      rowKey={(row) => row.key}
      rows={view.rows}
      columns={[
        {
          key: "label",
          header: "Fiscal quarter",
          rowHeader: true,
          render: (row) => (
            <span className="flex flex-col">
              {row.label}
              <span className="text-micro font-normal text-ink-muted">ends {row.endDate}</span>
            </span>
          ),
        },
        ...DOSSIER_METRICS.map((metric) => ({
          key: "cells" as const,
          id: metric.slug,
          header: metric.label,
          numeric: true,
          render: (row: QuarterRow) => (
            <LineageCell
              id={`lineage-${metric.slug}-${row.key}`}
              cell={row.cells[metric.slug]}
              metricLabel={metric.label}
              quarterLabel={row.label}
              currency={currency}
              scale={scale}
            />
          ),
        })),
      ]}
    />
  );
}

export function CoverageList({ view }: { view: DossierView }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {DOSSIER_METRICS.map((metric) => {
        const entry = view.coverage.find((candidate) => candidate.metric === metric.slug);
        return (
          <CoverageMeter
            key={metric.slug}
            label={metric.label}
            valid={entry?.quarters_valid ?? 0}
            expected={entry?.quarters_expected ?? 0}
          />
        );
      })}
    </div>
  );
}

export function FilingsTable({ filings }: { filings: readonly FilingReference[] }) {
  const rows = [...filings].sort((a, b) => b.filed_at.localeCompare(a.filed_at));
  return (
    <DataTable<FilingReference>
      id="filings"
      caption="Filings behind the values, newest first"
      rowKey={(filing) => filing.filing_id}
      rows={rows}
      columns={[
        { key: "accession_number", header: "Accession number", rowHeader: true },
        { key: "form", header: "Form" },
        { key: "period_end", header: "Period end" },
        { key: "filed_at", header: "Filed on", render: (filing) => dateOnly(filing.filed_at) },
        {
          key: "url",
          header: "Document",
          render: (filing) => {
            const href = safeExternalUrl(filing.url);
            return href ? (
              <a href={href} rel="noopener noreferrer" className="text-blue underline">
                Open on sec.gov
              </a>
            ) : (
              <span className="text-ink-muted">None (synthetic)</span>
            );
          },
        },
      ]}
    />
  );
}

const SEVERITY_TONE = { info: "info", warning: "warning", blocking: "negative" } as const;

export function QualityFlags({ dossier }: { dossier: CompanyDossier }) {
  if (dossier.quality_flags.length === 0) {
    return <p className="text-body text-ink-muted">No data quality issues are recorded.</p>;
  }
  return (
    <ul className="grid max-w-3xl gap-3">
      {dossier.quality_flags.map((flag) => (
        <li key={flag.code}>
          <Alert tone={SEVERITY_TONE[flag.severity]} title={flag.message} />
        </li>
      ))}
    </ul>
  );
}
