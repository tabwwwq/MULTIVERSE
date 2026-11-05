import { describe, expect, it } from "vitest";
import {
  COMPLETION_LABELS,
  EVENTS,
  REJECTED,
  TYPE_LABELS,
  eventById,
  firstDocument,
  formatMagnitude,
  humanReviewed,
  parseReviews,
  typeCounts,
  withReview,
  type LocalReview,
} from "../src/events/registry";

const review: LocalReview = {
  event_id: "evt-1",
  reviewer: "owner",
  decision: "confirmed",
  confidence: "high",
  notes: null,
  reviewed_at: "2026-11-06T12:00:00Z",
};

describe("event registry", () => {
  it("holds evidence and a named review for every event", () => {
    expect(EVENTS.length).toBeGreaterThan(0);
    for (const event of EVENTS) {
      expect(event.evidence.length).toBeGreaterThan(0);
      expect(event.evidence[0]?.url).toMatch(/^https:\/\/www\.sec\.gov\/Archives\//);
      expect(event.reviews[0]?.reviewer).toBeTruthy();
      expect(TYPE_LABELS[event.event_type]).toBeTruthy();
      expect(COMPLETION_LABELS[event.completion]).toBeTruthy();
    }
  });

  it("keeps what it rejected", () => {
    expect(REJECTED.length).toBeGreaterThan(0);
    expect(REJECTED.every((row) => row.reason.length > 0)).toBe(true);
  });

  it("counts every type, also the empty ones", () => {
    const counts = typeCounts([]);
    expect(Object.keys(counts)).toEqual(Object.keys(TYPE_LABELS));
    expect(Object.values(typeCounts(EVENTS)).reduce((a, b) => a + b, 0)).toBe(EVENTS.length);
  });

  it("writes a magnitude with its unit, or says it is unknown", () => {
    const base = EVENTS[0];
    if (!base) throw new Error("no events");
    const size = (value: number | null, unit: string) =>
      formatMagnitude({ ...base, magnitude: { value, unit, measures: "x" } } as typeof base);
    expect(size(2_600_000_000, "usd")).toBe("$2.60 billion");
    expect(size(85_000_000, "usd")).toBe("$85.0 million");
    expect(size(250_000, "usd")).toBe("$250,000");
    expect(size(83, "percent_of_workforce")).toBe("83% of the workforce");
    expect(size(100, "headcount")).toBe("100 people");
    expect(size(null, "unknown")).toBe("Unknown");
  });

  it("finds events and the date of their first document", () => {
    const base = EVENTS[0];
    if (!base) throw new Error("no events");
    expect(eventById(base.event_id)).toBe(base);
    expect(eventById("evt-none")).toBeUndefined();
    expect(firstDocument(base)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("counts only human reviews as human", () => {
    expect(humanReviewed(EVENTS)).toBe(
      EVENTS.filter((event) => event.reviews.some((row) => row.kind === "human")).length,
    );
  });

  it("reads stored reviews safely and keeps one per reviewer and event", () => {
    expect(parseReviews(null)).toEqual([]);
    expect(parseReviews("not json")).toEqual([]);
    expect(parseReviews('[{"nothing": 1}]')).toEqual([]);
    expect(parseReviews(JSON.stringify([review]))).toEqual([review]);
    const later = { ...review, decision: "rejected" as const };
    expect(withReview([review], later)).toEqual([later]);
    expect(withReview([review], { ...review, reviewer: "other" })).toHaveLength(2);
  });
});
