import type { Metadata } from "next";
import type { CompanyCandidate, Risk } from "@multiverse/contracts/sources";
import { Facts, TextList } from "@/components/sources/source-parts";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { specFor } from "@/decisions/catalog";
import { PageHeader, Section } from "@/layouts/page-header";
import {
  EVIDENCE_LABELS,
  LEVEL_LABELS,
  MAX_SCORE,
  PRIORITY_LABELS,
  RISK_CATEGORY_LABELS,
  SOURCE_CATALOG,
  sourceById,
} from "@/sources/catalog";

export const metadata: Metadata = { title: "Acquisition plan · Data Catalog" };

const sourceNames = (ids: readonly string[]) =>
  ids.map((id) => sourceById(id)?.name ?? id).join(", ");
const decisionNames = (types: readonly CompanyCandidate["decisions"][number][]) =>
  types.map((type) => specFor(type).label).join(", ");

const RISK_COLUMNS: ReadonlyArray<Column<Risk>> = [
  { key: "risk_id", header: "ID", rowHeader: true },
  {
    key: "title",
    header: "Risk",
    wrap: true,
    render: (row) => (
      <span className="flex flex-col gap-1">
        <span className="font-medium text-ink">{row.title}</span>
        <span className="text-micro">
          {RISK_CATEGORY_LABELS[row.category]} · {sourceNames(row.sources)}
        </span>
      </span>
    ),
  },
  {
    key: "likelihood",
    header: "Likelihood / impact",
    render: (row) => `${LEVEL_LABELS[row.likelihood]} / ${LEVEL_LABELS[row.impact]}`,
  },
  { key: "description", header: "What happens", wrap: true },
  {
    key: "mitigation",
    header: "Mitigation and check",
    wrap: true,
    render: (row) => (
      <span className="flex flex-col gap-1">
        <span>{row.mitigation}</span>
        <span className="text-micro text-ink-muted">Shows up as: {row.detection}</span>
      </span>
    ),
  },
  { key: "stage", header: "Stage", numeric: true },
];

type Sector = (typeof SOURCE_CATALOG.sectors)[number];
const SECTOR_COLUMNS: ReadonlyArray<Column<Sector>> = [
  { key: "sector", header: "Sector", rowHeader: true, wrap: true },
  { key: "priority", header: "Priority", render: (row) => PRIORITY_LABELS[row.priority] },
  { key: "sic_codes", header: "SIC codes", render: (row) => row.sic_codes.join(", ") },
  { key: "rationale", header: "Why", wrap: true },
  {
    key: "decisions",
    header: "Decisions it suits",
    wrap: true,
    render: (row) => (row.decisions.length > 0 ? decisionNames(row.decisions) : "None"),
  },
];

type Criterion = (typeof SOURCE_CATALOG.rubric)[number];
const RUBRIC_COLUMNS: ReadonlyArray<Column<Criterion>> = [
  { key: "criterion_id", header: "ID", rowHeader: true },
  { key: "title", header: "Criterion", wrap: true },
  { key: "weight", header: "Weight", numeric: true },
  { key: "how_checked", header: "How it is checked", wrap: true },
];

const CANDIDATE_COLUMNS: ReadonlyArray<Column<CompanyCandidate>> = [
  { key: "rank", header: "Rank", numeric: true },
  {
    key: "name",
    header: "Company",
    rowHeader: true,
    render: (row) => (
      <span className="flex flex-col gap-1">
        <span>{row.name}</span>
        <span className="text-micro font-normal text-ink-muted">
          {row.ticker ?? "No ticker"} · CIK {row.cik}
          {row.status === "acquired" ? " · Acquired" : ""}
        </span>
      </span>
    ),
  },
  {
    key: "sic",
    header: "SIC",
    wrap: true,
    render: (row) => `${row.sic} ${row.sic_description} (${PRIORITY_LABELS[row.sector_priority]})`,
  },
  {
    key: "total",
    header: "Score",
    numeric: true,
    render: (row) => {
      const verified = row.scores.filter((score) => score.evidence === "verified").length;
      return (
        <span className="flex flex-col gap-1">
          <span>
            {row.total} of {MAX_SCORE}
          </span>
          <span className="text-micro text-ink-muted">
            {verified} of {row.scores.length} verified
          </span>
        </span>
      );
    },
  },
  {
    key: "decisions",
    header: "Decisions",
    wrap: true,
    render: (row) => decisionNames(row.decisions),
  },
  { key: "concerns", header: "To watch", wrap: true, render: (row) => row.concerns.join(" ") },
];

export default function AcquisitionPlanPage() {
  const catalog = SOURCE_CATALOG;
  return (
    <>
      <PageHeader
        title="Acquisition plan"
        summary="The order in which data would be acquired, what can go wrong, and which companies and sectors come first."
        meta={<Badge tone="warning">Nothing runs without the owner&apos;s decision</Badge>}
      />

      <Section
        id="steps"
        title="Steps"
        intro="Each step names its sources, volume, storage and checks. Steps with an owner decision do not start before it."
      >
        <ol className="flex max-w-4xl flex-col gap-4">
          {catalog.acquisition_plan.map((step) => (
            <li key={step.step} className="rounded-panel border border-line bg-surface p-5">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-display text-h4 font-semibold text-ink">
                  <span className="text-ink-muted tabular-nums">{step.step}. </span>
                  {step.title}
                </h3>
                <span className="flex flex-wrap gap-2">
                  <Badge>Stage {String(step.stage).padStart(2, "0")}</Badge>
                  {step.owner_decision ? <Badge tone="warning">Owner decision needed</Badge> : null}
                </span>
              </div>
              <Facts
                items={[
                  { term: "Sources", detail: sourceNames(step.sources) },
                  { term: "Scope", detail: step.scope },
                  { term: "Volume", detail: step.volume },
                  { term: "Storage", detail: step.storage },
                  { term: "Checks", detail: <TextList items={step.checks} /> },
                  ...(step.owner_decision
                    ? [{ term: "Owner decides", detail: step.owner_decision }]
                    : []),
                ]}
              />
            </li>
          ))}
        </ol>
      </Section>

      <Section
        id="risks"
        title="Source risk register"
        intro="Risks of the sources themselves, with the stage that implements each mitigation."
      >
        <DataTable
          id="risk-register"
          caption={`${catalog.risks.length} risks`}
          columns={RISK_COLUMNS}
          rows={catalog.risks}
          rowKey={(row) => row.risk_id}
        />
      </Section>

      <Section
        id="sectors"
        title="Sector priority"
        intro="By suitability for the six decision types and for clean statements, not by fame."
      >
        <DataTable
          id="sector-priority"
          caption="Sectors in order of priority"
          columns={SECTOR_COLUMNS}
          rows={catalog.sectors}
          rowKey={(row) => row.sector}
        />
      </Section>

      <Section
        id="companies"
        title="First ten companies"
        intro={`Ranked by a scoring rubric (at most ${MAX_SCORE} points). Ties keep the sectors varied.`}
      >
        <div className="mb-6 max-w-3xl">
          <Alert tone="warning" title="Real companies, no data yet">
            These are real public companies proposed for the first download. MULTIVERSE shows no
            figures about them. CIK, SIC, fiscal year end, filer category and tickers were checked
            on the SEC submissions pages on {catalog.verified_on}; the other scores are expectations
            that Stages 10 and 11 confirm or correct.
          </Alert>
        </div>
        <div className="flex flex-col gap-8">
          <DataTable
            id="candidates"
            caption="Candidates for the first acquisition"
            columns={CANDIDATE_COLUMNS}
            rows={catalog.candidates}
            rowKey={(row) => row.cik}
          />
          <DataTable
            id="rubric"
            caption="Scoring rubric: points 0 to 2 times the weight"
            columns={RUBRIC_COLUMNS}
            rows={catalog.rubric}
            rowKey={(row) => row.criterion_id}
          />
          <p className="max-w-prose text-small text-ink-muted">
            Evidence per score: {EVIDENCE_LABELS.verified} means read from an official SEC page;{" "}
            {EVIDENCE_LABELS.expected.toLowerCase()} means a reasoned expectation.
          </p>
        </div>
      </Section>

      <div className="mt-16">
        <ButtonLink href="/data-catalog" variant="secondary">
          All sources
        </ButtonLink>
      </div>
    </>
  );
}
