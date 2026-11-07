import type { Metadata } from "next";
import Form from "next/form";
import Link from "next/link";
import { formatAmount, unitLabel } from "@/companies/format";
import { DOSSIER_METRICS } from "@/companies/labels";
import type { RawParams } from "@/companies/params";
import { cutoffChoices } from "@/companies/pit";
import { realCompany } from "@/companies/real-data";
import { getCompanyRepository } from "@/companies/repository";
import { currentName } from "@/companies/search";
import { SyntheticBadge } from "@/components/companies/company-badges";
import { KNOWLEDGE_LABELS, KnowledgeTimeline } from "@/components/time-machine/knowledge-timeline";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { SelectField } from "@/components/ui/field";
import { PageHeader, Section } from "@/layouts/page-header";
import {
  type CellKnowledge,
  type ComparisonRow,
  compareCutoffs,
  defaultCutoffs,
  medianLagDays,
} from "@/time-machine/compare";

export const metadata: Metadata = { title: "Time Machine" };

interface PageProps {
  searchParams: Promise<RawParams>;
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

const CELL_STYLES: Record<CellKnowledge["knowledge"], string> = {
  known_at_first: "text-ink",
  new_in_between: "rounded-sm bg-violet/15 px-1.5 py-0.5 text-ink ring-1 ring-violet/60",
  not_yet: "text-ink-muted line-through decoration-line-strong",
  missing: "text-ink-muted",
};

function Cell({ cell, scale }: { cell: CellKnowledge | undefined; scale: "m" | "bn" }) {
  if (!cell || cell.value === null) return <span className="text-ink-muted">—</span>;
  const state = cell.knowledge === "missing" ? "" : KNOWLEDGE_LABELS[cell.knowledge];
  return (
    <span className={`relative ${CELL_STYLES[cell.knowledge]}`} title={state}>
      {formatAmount(cell.value, scale)}
      <span className="sr-only"> ({state})</span>
    </span>
  );
}

export default async function TimeMachinePage({ searchParams }: PageProps) {
  const raw = await searchParams;
  const repository = getCompanyRepository();
  const ids = await repository.listIds();
  const dossiers = (await Promise.all(ids.map((id) => repository.getDossier(id)))).filter(
    (dossier) => dossier !== null && cutoffChoices(dossier).length >= 2,
  );
  const wanted = first(raw["company"]);
  const dossier = dossiers.find((item) => item?.company.company_id === wanted) ?? dossiers[0];
  if (!dossier) {
    return (
      <PageHeader title="Time Machine" summary="No company has two quarters to compare yet." />
    );
  }
  const choices = cutoffChoices(dossier);
  const defaults = defaultCutoffs(dossier) as [string, string];
  const pick = (name: string, fallback: string) => {
    const value = first(raw[name]);
    return value !== undefined && choices.includes(value) ? value : fallback;
  };
  const comparison = compareCutoffs(dossier, pick("from", defaults[0]), pick("to", defaults[1]));
  const lag = medianLagDays(comparison.quarters);
  const largest = Math.max(
    ...comparison.rows.map((row) => Math.abs(Number(row.cells["revenue"]?.value ?? 0))),
  );
  const scale = largest >= 1e10 ? "bn" : "m";
  const currency = dossier.company.reporting_currency;
  const name = currentName(dossier.company).name;
  const synthetic = realCompany(dossier.company.company_id) === null;

  const columns: Column<ComparisonRow>[] = [
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
      render: (row: ComparisonRow) => <Cell cell={row.cells[metric.slug]} scale={scale} />,
    })),
  ];

  return (
    <>
      <PageHeader
        title="Time Machine"
        summary="What was public about a company on two dates, and what became public in between. A quarter counts from the day its filing was published, not from the end of its period."
        meta={synthetic ? <SyntheticBadge /> : undefined}
      />

      <Form action="/time-machine" className="mb-10 flex flex-wrap items-end gap-3">
        <div className="min-w-72 flex-1 md:max-w-md">
          <SelectField
            id="tm-company"
            name="company"
            label="Company"
            defaultValue={dossier.company.company_id}
          >
            {dossiers.map((item) =>
              item ? (
                <option key={item.company.company_id} value={item.company.company_id}>
                  {currentName(item.company).name}
                  {realCompany(item.company.company_id) === null ? " (fictional)" : ""}
                </option>
              ) : null,
            )}
          </SelectField>
        </div>
        <div className="min-w-44">
          <SelectField id="tm-from" name="from" label="First date" defaultValue={comparison.first}>
            {choices.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </SelectField>
        </div>
        <div className="min-w-44">
          <SelectField id="tm-to" name="to" label="Second date" defaultValue={comparison.second}>
            {choices.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </SelectField>
        </div>
        <Button type="submit" variant="secondary">
          Compare
        </Button>
      </Form>

      <dl className="mb-10 grid gap-4 sm:grid-cols-3">
        {[
          {
            label: `Public on ${comparison.first}`,
            value: comparison.knownAtFirst,
            tone: "bg-mint",
          },
          { label: "Became public in between", value: comparison.newInBetween, tone: "bg-violet" },
          {
            label: `Not public on ${comparison.second}`,
            value: comparison.notYet,
            tone: "bg-line-strong",
          },
        ].map((item) => (
          <div
            key={item.label}
            className="flex flex-col gap-1 rounded-panel border border-line bg-surface p-4"
          >
            <dt className="flex items-center gap-2 text-small text-ink-muted">
              <span
                aria-hidden="true"
                className={`inline-block size-2.5 rounded-full ${item.tone}`}
              />
              {item.label}
            </dt>
            <dd className="font-display text-h3 text-ink tabular-nums">
              {item.value} {item.value === 1 ? "quarter" : "quarters"}
            </dd>
          </div>
        ))}
      </dl>

      <Section
        id="timeline"
        title={`${name}: the lag between a quarter and its filing`}
        intro={
          lag === null
            ? "No filing dates are known for these quarters."
            : `On the median quarter the filing came ${lag} days after the period ended. A model that read the quarter on its last day would have seen the future.`
        }
      >
        <div className="rounded-panel border border-line bg-surface p-4 md:p-6">
          <KnowledgeTimeline comparison={comparison} />
        </div>
      </Section>

      <Section
        id="values"
        title="Values on the second date"
        intro={`In ${unitLabel(currency, scale)}. A figure counts from the filing it was last reported in, which can be the comparative column of a later filing: outlined figures were reported between ${comparison.first} and ${comparison.second}, struck-through ones only after ${comparison.second}.`}
      >
        <DataTable<ComparisonRow>
          id="time-machine"
          caption={`${name}, quarters ending by ${comparison.second}`}
          rows={comparison.rows}
          rowKey={(row) => row.key}
          columns={columns}
        />
        <p className="mt-4 text-small text-ink-muted">
          Each value with its filing and lineage is in the{" "}
          <Link
            href={`/dossier/${dossier.company.company_id}?asOf=${comparison.second}`}
            className="text-mint underline underline-offset-4"
          >
            dossier as known on {comparison.second}
          </Link>
          .
        </p>
      </Section>

      {synthetic ? (
        <Alert tone="warning" title="Fictional company">
          Names, figures and filing dates are invented to show how the comparison works.
        </Alert>
      ) : null}
    </>
  );
}
