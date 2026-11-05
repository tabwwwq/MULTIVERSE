import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ReviewForm } from "@/components/events/review-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  COMPLETION_LABELS,
  COMPLETION_TONES,
  EVENTS,
  TYPE_LABELS,
  UNKNOWN_LABELS,
  eventById,
  formatMagnitude,
} from "@/events/registry";
import { PageHeader, Section } from "@/layouts/page-header";
import { safeExternalUrl } from "@/lib/safe-url";

export const dynamicParams = false;

export function generateStaticParams() {
  return EVENTS.map((event) => ({ eventId: event.event_id }));
}

interface PageProps {
  params: Promise<{ eventId: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const event = eventById((await params).eventId);
  return { title: event ? `${event.company}: ${TYPE_LABELS[event.event_type]}` : "Event" };
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-micro text-ink-muted">{label}</dt>
      <dd className="text-small text-ink">{value}</dd>
    </div>
  );
}

export default async function EventPage({ params }: PageProps) {
  const event = eventById((await params).eventId);
  if (!event) notFound();
  const unknown = event.unknown_fields ?? [];
  const confounders = event.confounded_by ?? [];
  const funding = event.funding;
  return (
    <>
      <PageHeader
        title={event.company}
        summary={`${TYPE_LABELS[event.event_type]}, SIC division ${event.division}${event.deregistered ? ", later left EDGAR reporting" : ""}.`}
        meta={
          <Badge tone={COMPLETION_TONES[event.completion]}>
            {COMPLETION_LABELS[event.completion]}
          </Badge>
        }
      />
      <Section id="treatment" title="Intention and execution">
        <dl className="grid gap-4 md:grid-cols-2">
          <Fact
            label="Announced intention"
            value={event.intention ?? "None in the documents read"}
          />
          <Fact label="Executed" value={event.executed ?? "Not documented"} />
          <Fact label="Magnitude" value={formatMagnitude(event)} />
          <Fact label="What the number measures" value={event.magnitude.measures} />
          <Fact label="Effective date" value={event.effective_on ?? "Unknown"} />
          <Fact
            label="Reporting lag"
            value={
              event.reporting_lag_days === null || event.reporting_lag_days === undefined
                ? "Unknown"
                : `${event.reporting_lag_days} days`
            }
          />
          <Fact label="Funding" value={funding?.note ?? "Unknown"} />
        </dl>
      </Section>
      {unknown.length > 0 ? (
        <Section id="unknown" title="Unknown">
          <p className="text-small text-ink-muted">
            {unknown.map((field) => UNKNOWN_LABELS[field] ?? field).join(", ")}
          </p>
        </Section>
      ) : null}
      {confounders.length > 0 ? (
        <Section id="confounded" title="Happening at the same time">
          <Alert tone="warning" title="This event does not stand alone">
            <ul className="list-disc pl-5">
              {confounders.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </Alert>
        </Section>
      ) : null}
      <Section id="evidence" title="Evidence">
        <ul className="flex flex-col gap-3">
          {event.evidence.map((item) => (
            <li key={item.accession} className="rounded-panel border border-line bg-surface p-4">
              <p className="text-small text-ink">{item.summary}</p>
              <p className="mt-1 text-micro text-ink-muted">
                {item.form}
                {item.item ? `, Item ${item.item}` : ""}, {item.locator}, public from{" "}
                {item.filed_at.slice(0, 16).replace("T", " ")} UTC.
              </p>
              <a
                href={safeExternalUrl(item.url) ?? "#"}
                className="text-small text-ink underline"
                rel="noreferrer"
                target="_blank"
              >
                Read the filing on sec.gov
              </a>
            </li>
          ))}
        </ul>
      </Section>
      <Section id="reviews" title="Reviews">
        <ul className="mb-4 flex flex-col gap-2 text-small text-ink-muted">
          {event.reviews.map((review) => (
            <li key={review.reviewer}>
              {review.reviewer} ({review.kind === "ai" ? "AI" : "human"}): {review.decision},{" "}
              {review.confidence} confidence. {review.notes}
            </li>
          ))}
        </ul>
        <ReviewForm eventId={event.event_id} />
      </Section>
    </>
  );
}
