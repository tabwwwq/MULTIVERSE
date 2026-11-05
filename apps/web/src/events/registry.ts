import { EVENT_REGISTRY, type CorporateEvent } from "@multiverse/contracts/events";
import type { BadgeTone } from "@/components/ui/badge";

/**
 * The verified event registry on screen (Stage 19). Facts come from reviewers reading filings;
 * the screen adds nothing. Reviews made here stay in this browser until they are downloaded
 * and merged with `python -m multiverse_pipelines.events reviews`.
 */

export const EVENTS: readonly CorporateEvent[] = EVENT_REGISTRY.events;
export const REJECTED = EVENT_REGISTRY.rejected ?? [];
/** Events of each type the audit asks for before causal work may start. */
export const MINIMUM_PER_TYPE = 30;
export const REVIEWS_KEY = "multiverse.event-reviews";

export const TYPE_LABELS: Record<CorporateEvent["event_type"], string> = {
  rnd_change: "R&D change",
  acquisition: "Acquisition",
  layoff: "Layoff",
  divestiture: "Divestiture",
  capex_change: "Capex change",
  refinancing: "Refinancing",
};

export const COMPLETION_LABELS: Record<CorporateEvent["completion"], string> = {
  announced: "Announced only",
  partial: "Partly done",
  completed: "Completed",
  terminated: "Terminated",
  unknown: "Unknown",
};

export const COMPLETION_TONES: Record<CorporateEvent["completion"], BadgeTone> = {
  announced: "warning",
  partial: "warning",
  completed: "mint",
  terminated: "negative",
  unknown: "neutral",
};

export const UNKNOWN_LABELS: Record<string, string> = {
  announced_at: "First announcement",
  effective_on: "Effective date",
  reporting_lag_days: "Reporting lag",
  magnitude: "Magnitude",
  funding: "Funding mix",
};

const UNIT_SUFFIX: Record<string, string> = {
  percent_of_workforce: "% of the workforce",
  percent_change: "% change",
  points_of_revenue: " points of revenue",
  headcount: " people",
};

export function eventById(id: string): CorporateEvent | undefined {
  return EVENTS.find((event) => event.event_id === id);
}

export function formatMagnitude(event: CorporateEvent): string {
  const { value, unit } = event.magnitude;
  if (value === null || value === undefined) return "Unknown";
  if (unit === "usd") {
    if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(2)} billion`;
    if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(1)} million`;
    return `$${value.toLocaleString("en-US")}`;
  }
  return `${value.toLocaleString("en-US")}${unit ? (UNIT_SUFFIX[unit] ?? "") : ""}`;
}

export function firstDocument(event: CorporateEvent): string {
  const moments = event.evidence.map((item) => item.filed_at).sort();
  return (moments[0] ?? "").slice(0, 10);
}

export function typeCounts(events: readonly CorporateEvent[]): Record<string, number> {
  const counts: Record<string, number> = Object.fromEntries(
    Object.keys(TYPE_LABELS).map((type) => [type, 0]),
  );
  for (const event of events) counts[event.event_type] = (counts[event.event_type] ?? 0) + 1;
  return counts;
}

export function humanReviewed(events: readonly CorporateEvent[]): number {
  return events.filter((event) => event.reviews.some((review) => review.kind === "human")).length;
}

export interface LocalReview {
  event_id: string;
  reviewer: string;
  decision: "confirmed" | "corrected" | "rejected" | "unsure";
  confidence: "high" | "medium" | "low";
  notes: string | null;
  reviewed_at: string;
}

function isReview(value: unknown): value is LocalReview {
  const row = value as Partial<LocalReview> | null;
  return typeof row?.event_id === "string" && typeof row.reviewer === "string";
}

export function parseReviews(text: string | null): LocalReview[] {
  if (!text) return [];
  try {
    const rows: unknown = JSON.parse(text);
    return Array.isArray(rows) ? rows.filter(isReview) : [];
  } catch {
    return [];
  }
}

/** One review per reviewer and event: a later one replaces it. */
export function withReview(reviews: readonly LocalReview[], review: LocalReview): LocalReview[] {
  return [
    ...reviews.filter(
      (row) => !(row.event_id === review.event_id && row.reviewer === review.reviewer),
    ),
    review,
  ];
}
