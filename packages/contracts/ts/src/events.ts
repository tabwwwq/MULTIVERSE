/**
 * The verified event registry (Stage 19). The JSON is written by reviewers, validated by the
 * Python contracts in CI, and holds facts and addresses of public filings only.
 */
import type { EventRegistry } from "./generated/contracts";
import data from "../../../../data/events/registry.json";

export type CorporateEvent = EventRegistry["events"][number];
export type RejectedCandidate = NonNullable<EventRegistry["rejected"]>[number];

// JSON imports widen literal types; the Python contracts validate the file in CI.
export const EVENT_REGISTRY: EventRegistry = data as unknown as EventRegistry;
