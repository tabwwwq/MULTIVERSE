import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  AccessBadge,
  DocLinks,
  DownloadBadge,
  Facts,
  TextList,
} from "@/components/sources/source-parts";
import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { PageHeader, Section } from "@/layouts/page-header";
import {
  AUTHENTICATION_LABELS,
  FIELD_TYPE_LABELS,
  FORMAT_LABELS,
  KEY_LABELS,
  REDISTRIBUTION_LABELS,
  RESALE_LABELS,
  ROLE_LABELS,
  SOURCES,
  sourceById,
} from "@/sources/catalog";
import type { SourceDataset } from "@multiverse/contracts/sources";

export const dynamicParams = false;

export function generateStaticParams() {
  return SOURCES.map((source) => ({ sourceId: source.source_id }));
}

interface PageProps {
  params: Promise<{ sourceId: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const source = sourceById((await params).sourceId);
  return source ? { title: `${source.name} · Data Catalog` } : {};
}

type Field = SourceDataset["fields"][number];

const FIELD_COLUMNS: ReadonlyArray<Column<Field>> = [
  {
    key: "name",
    header: "Field",
    rowHeader: true,
    render: (row) => <code className="text-micro [overflow-wrap:anywhere]">{row.name}</code>,
  },
  { key: "type", header: "Type", render: (row) => FIELD_TYPE_LABELS[row.type] },
  { key: "role", header: "Role", render: (row) => ROLE_LABELS[row.role] },
  { key: "description", header: "Meaning", wrap: true },
];

function DatasetBlock({ dataset }: { dataset: SourceDataset }) {
  return (
    <section
      aria-labelledby={`${dataset.dataset_id}-title`}
      className="flex flex-col gap-4 border-t border-line pt-6 first:border-t-0 first:pt-0"
    >
      <h3
        id={`${dataset.dataset_id}-title`}
        className="font-display text-h4 font-semibold text-ink"
      >
        {dataset.title}
      </h3>
      <p className="max-w-prose text-body text-ink-muted">{dataset.description}</p>
      <Facts
        items={[
          {
            term: "Addresses",
            detail: (
              <ul className="flex flex-col gap-1">
                {dataset.endpoints.map((endpoint) => (
                  <li key={endpoint}>
                    <code className="text-micro">{endpoint}</code>
                  </li>
                ))}
              </ul>
            ),
          },
          {
            term: "Formats",
            detail: dataset.formats.map((format) => FORMAT_LABELS[format]).join(", "),
          },
          { term: "Updates", detail: dataset.update_frequency },
          { term: "Known from", detail: dataset.knowledge_time },
          { term: "Revisions", detail: dataset.revision_semantics },
          { term: "Coverage", detail: dataset.coverage },
          ...(dataset.size ? [{ term: "Size", detail: dataset.size }] : []),
          { term: "Identifiers", detail: dataset.identifiers.join("; ") },
          { term: "Recorded with each file", detail: <TextList items={dataset.provenance} /> },
        ]}
      />
      <DataTable
        id={`${dataset.dataset_id}-fields`}
        caption={`Data dictionary: ${dataset.title}`}
        columns={FIELD_COLUMNS}
        rows={dataset.fields}
        rowKey={(row) => row.name}
      />
      <DocLinks docs={dataset.docs} />
    </section>
  );
}

export default async function SourcePage({ params }: PageProps) {
  const source = sourceById((await params).sourceId);
  if (!source) notFound();
  const { licence, rate_limit: rate } = source;

  return (
    <>
      <PageHeader
        title={source.name}
        summary={`${source.publisher} · ${source.region} · source priority ${source.priority} of docs/04`}
        meta={
          <>
            <AccessBadge access={source.access} />
            <DownloadBadge source={source} />
          </>
        }
      />
      <div className="mb-6 max-w-3xl">
        <Alert tone="info" title="Metadata only">
          {source.download.note} Documentation checked on {source.verified_on}.
        </Alert>
      </div>

      <Section id="access" title="Access and key">
        <Facts
          items={[
            { term: "Authentication", detail: AUTHENTICATION_LABELS[source.authentication] },
            { term: "Key", detail: KEY_LABELS[source.key_status] },
            { term: "Request rules", detail: <TextList items={source.request_rules} /> },
          ]}
        />
      </Section>

      <Section id="licence" title="Licence and reuse">
        <Facts
          items={[
            { term: "Terms", detail: licence.name },
            { term: "Summary", detail: licence.summary },
            { term: "Redistribution", detail: REDISTRIBUTION_LABELS[licence.redistribution] },
            { term: "Resale", detail: RESALE_LABELS[licence.resale] },
            ...(licence.attribution ? [{ term: "Attribution", detail: licence.attribution }] : []),
            ...(licence.exceptions ? [{ term: "Exceptions", detail: licence.exceptions }] : []),
          ]}
        />
      </Section>

      <Section id="limits" title="Request limits, retries and checksums">
        <Facts
          items={[
            { term: "Documented limit", detail: rate.documented },
            {
              term: "Rate MULTIVERSE will use",
              detail: `${rate.chosen_requests_per_second} requests per second at most`,
            },
            { term: "Retries", detail: source.retry_policy },
            { term: "Checksums", detail: source.checksum_policy },
          ]}
        />
      </Section>

      <Section id="docs" title="Official documentation">
        <DocLinks docs={source.docs} />
      </Section>

      <Section
        id="datasets"
        title="Datasets and data dictionary"
        intro="Addresses are patterns: values in braces are filled in per request. Knowledge time is what point-in-time rules use."
      >
        <div className="flex flex-col gap-10">
          {source.datasets.map((dataset) => (
            <DatasetBlock key={dataset.dataset_id} dataset={dataset} />
          ))}
        </div>
      </Section>

      {source.notes.length > 0 ? (
        <Section id="notes" title="Notes">
          <div className="max-w-prose text-body text-ink-muted">
            <TextList items={source.notes} />
          </div>
        </Section>
      ) : null}

      <div className="mt-16 flex flex-wrap gap-3">
        <ButtonLink href="/data-catalog" variant="secondary">
          All sources
        </ButtonLink>
        <ButtonLink href="/data-catalog/plan" variant="secondary">
          Acquisition plan
        </ButtonLink>
      </div>
    </>
  );
}
