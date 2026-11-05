import type { CorporateEvent } from "@multiverse/contracts/events";
import type { Metadata } from "next";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import {
  COMPLETION_LABELS,
  COMPLETION_TONES,
  EVENTS,
  MINIMUM_PER_TYPE,
  REJECTED,
  TYPE_LABELS,
  firstDocument,
  formatMagnitude,
  humanReviewed,
  typeCounts,
} from "@/events/registry";
import { PageHeader, Section } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Event Registry" };

interface PageProps {
  searchParams: Promise<{ type?: string | string[] }>;
}

const COLUMNS: ReadonlyArray<Column<CorporateEvent>> = [
  {
    key: "company",
    header: "Company",
    rowHeader: true,
    wrap: true,
    render: (event) => (
      <Link href={`/events/${event.event_id}`} className="text-ink underline">
        {event.company}
      </Link>
    ),
  },
  { key: "event_type", header: "Type", render: (event) => TYPE_LABELS[event.event_type] },
  { key: "evidence", header: "First document", render: firstDocument },
  { key: "magnitude", header: "Magnitude", wrap: true, render: formatMagnitude },
  {
    key: "completion",
    header: "Status",
    render: (event) => (
      <Badge tone={COMPLETION_TONES[event.completion]}>{COMPLETION_LABELS[event.completion]}</Badge>
    ),
  },
  {
    key: "reviews",
    header: "Reviews",
    render: (event) =>
      event.reviews.map((review) => `${review.reviewer} (${review.kind})`).join(", "),
  },
];

export default async function EventsPage({ searchParams }: PageProps) {
  const { type } = await searchParams;
  const chosen = typeof type === "string" && type in TYPE_LABELS ? type : null;
  const rows = chosen ? EVENTS.filter((event) => event.event_type === chosen) : EVENTS;
  const counts = typeCounts(EVENTS);
  const human = humanReviewed(EVENTS);
  return (
    <>
      <PageHeader
        title="Event Registry"
        summary="Corporate decisions read in their own filings. An announcement stays an announcement until a document says it was done."
        meta={<Badge tone="warning">Single review by AI</Badge>}
      />
      <Section
        id="status"
        title="What this sample can carry"
        intro={`${EVENTS.length + REJECTED.length} filings read, ${EVENTS.length} events, ${REJECTED.length} rejected and kept.`}
      >
        <Alert tone="warning" title="Causal work is blocked">
          The audit asks for {MINIMUM_PER_TYPE} events of each type, a human review on half of them
          and two reviewers. Human reviews so far: {human}. Nothing here may be read as an effect of
          a decision.
        </Alert>
      </Section>
      <Section id="events" title="Events">
        <nav aria-label="Filter by type" className="mb-4 flex flex-wrap gap-2">
          <ButtonLink href="/events" size="sm" variant={chosen ? "secondary" : "primary"}>
            All ({EVENTS.length})
          </ButtonLink>
          {Object.entries(TYPE_LABELS).map(([key, label]) => (
            <ButtonLink
              key={key}
              href={`/events?type=${key}`}
              size="sm"
              variant={chosen === key ? "primary" : "secondary"}
            >
              {label} ({counts[key]})
            </ButtonLink>
          ))}
        </nav>
        <DataTable
          id="events-table"
          caption="Events of the registry"
          columns={COLUMNS}
          rows={rows}
          rowKey={(event) => event.event_id}
        />
      </Section>
      <Section
        id="rejected"
        title="Read and rejected"
        intro="Kept on purpose: a sample that hides its misses cannot be trusted."
      >
        <ul className="flex flex-col gap-2 text-small text-ink-muted">
          {REJECTED.map((row) => (
            <li key={row.candidate_id}>{row.reason}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}
