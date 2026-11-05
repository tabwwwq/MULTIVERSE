import type { JobStatus, JobView } from "@multiverse/contracts";
import { describe, expect, it } from "vitest";
import {
  ACTION_LABELS,
  STATUS_LABELS,
  STATUS_TONES,
  actionsFor,
  formatDuration,
  silentFor,
} from "../src/models/jobs";

function job(status: JobStatus, changes: Partial<JobView> = {}): JobView {
  return {
    status,
    approved_at: "2026-11-05T20:00:00Z",
    last_heartbeat: "2026-11-05T20:00:00Z",
    ...changes,
  } as JobView;
}

const STATES: JobStatus[] = [
  "queued",
  "validating",
  "running",
  "pause_requested",
  "paused",
  "stop_requested",
  "stopped",
  "failed",
  "completed",
];

describe("training jobs", () => {
  it("names every state of the contract", () => {
    for (const status of STATES) {
      expect(STATUS_LABELS[status]).toBeTruthy();
      expect(STATUS_TONES[status]).toBeTruthy();
    }
  });

  it("offers only what the state of a job allows", () => {
    expect(actionsFor(job("queued", { approved_at: null }))).toEqual(["approve", "stop"]);
    expect(actionsFor(job("queued"))).toEqual(["stop"]);
    expect(actionsFor(job("running"))).toEqual(["pause", "stop"]);
    expect(actionsFor(job("pause_requested"))).toEqual(["stop"]);
    expect(actionsFor(job("stop_requested"))).toEqual([]);
    expect(actionsFor(job("paused"))).toEqual(["resume", "stop"]);
    expect(actionsFor(job("stopped"))).toEqual(["resume"]);
    expect(actionsFor(job("failed"))).toEqual(["resume"]);
    expect(actionsFor(job("completed"))).toEqual([]);
  });

  it("says that stop and pause wait for a checkpoint", () => {
    expect(ACTION_LABELS.stop).toContain("after checkpoint");
    expect(ACTION_LABELS.pause).toContain("after checkpoint");
  });

  it("writes durations a person reads", () => {
    expect(formatDuration(42.4)).toBe("42 s");
    expect(formatDuration(125)).toBe("2 min 5 s");
    expect(formatDuration(3720)).toBe("1 h 2 min");
  });

  it("watches heartbeats only of jobs a worker should hold", () => {
    const now = Date.parse("2026-11-05T20:01:30Z");
    expect(silentFor(job("running"), now)).toBe(90);
    expect(silentFor(job("stop_requested"), now)).toBe(90);
    expect(silentFor(job("paused"), now)).toBeNull();
    expect(silentFor(job("running", { last_heartbeat: null }), now)).toBeNull();
  });
});
