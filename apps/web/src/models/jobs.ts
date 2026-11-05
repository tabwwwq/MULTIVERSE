import type { JobLogLine, JobStatus, JobView } from "@multiverse/contracts";
import type { BadgeTone } from "@/components/ui/badge";

/**
 * Training jobs as the screen sees them (Stage 18). The worker owns the state; the screen
 * reads it and passes on requests, so closing the browser changes nothing.
 */

/** The API of this machine: `npm run dev:api` serves it, nothing public does. */
export const API_URL = "http://127.0.0.1:8000/api/v1";
export const POLL_MS = 2000;
/** Three missed heartbeats of the default lease: the worker has probably died. */
export const STALE_SECONDS = 60;

export const STATUS_LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  validating: "Validating",
  running: "Running",
  pause_requested: "Pause requested",
  paused: "Paused",
  stop_requested: "Stop requested",
  stopped: "Stopped",
  failed: "Failed",
  completed: "Completed",
};

export const STATUS_TONES: Record<JobStatus, BadgeTone> = {
  queued: "neutral",
  validating: "blue",
  running: "blue",
  pause_requested: "warning",
  paused: "violet",
  stop_requested: "warning",
  stopped: "violet",
  failed: "negative",
  completed: "mint",
};

const WORKING: readonly JobStatus[] = [
  "validating",
  "running",
  "pause_requested",
  "stop_requested",
];

export type JobAction = "approve" | "pause" | "stop" | "resume";

export const ACTION_LABELS: Record<JobAction, string> = {
  approve: "Approve estimate",
  pause: "Pause after checkpoint",
  stop: "Stop after checkpoint",
  resume: "Resume",
};

/** What the owner may ask of a job in its current state. */
export function actionsFor(job: JobView): JobAction[] {
  if (job.status === "queued") {
    return job.approved_at ? ["stop"] : ["approve", "stop"];
  }
  if (job.status === "running") return ["pause", "stop"];
  if (job.status === "validating" || job.status === "pause_requested") return ["stop"];
  if (job.status === "paused") return ["resume", "stop"];
  if (job.status === "stopped" || job.status === "failed") return ["resume"];
  return [];
}

export function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole} s`;
  const minutes = Math.floor(whole / 60);
  if (minutes < 60) return `${minutes} min ${whole % 60} s`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

/** Seconds since the last heartbeat of a job a worker should hold; null when none should. */
export function silentFor(job: JobView, now: number): number | null {
  if (!WORKING.includes(job.status) || !job.last_heartbeat) return null;
  return Math.max(0, (now - Date.parse(job.last_heartbeat)) / 1000);
}

async function read<T>(path: string, init?: RequestInit): Promise<T> {
  const answer = await fetch(`${API_URL}${path}`, init);
  if (!answer.ok) {
    const body = (await answer.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `The service answered ${answer.status}`);
  }
  return (await answer.json()) as T;
}

export function fetchJobs(signal?: AbortSignal): Promise<JobView[]> {
  return read<JobView[]>("/jobs", signal ? { signal } : undefined);
}

export function fetchLogs(jobId: string): Promise<JobLogLine[]> {
  return read<JobLogLine[]>(`/jobs/${jobId}/logs`);
}

export function act(jobId: string, action: JobAction): Promise<JobView> {
  return read<JobView>(`/jobs/${jobId}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: action === "approve" ? JSON.stringify({ by: "owner" }) : "{}",
  });
}
