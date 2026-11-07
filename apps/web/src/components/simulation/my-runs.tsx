"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import {
  STATUS_LABELS,
  STATUS_TONES,
  fetchJobs,
  isSimulation,
  type SimulationJob,
} from "@/models/jobs";

/** Runs of this computer: they live with the local engine, not in the static site. */
export function MyRuns() {
  const [jobs, setJobs] = useState<SimulationJob[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchJobs(controller.signal)
      .then((found) => setJobs(found.filter(isSimulation)))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  if (!jobs) {
    return (
      <p className="text-body text-ink-muted">
        Runs appear here while the engine is on: start it with <code>npm run app</code>.
      </p>
    );
  }
  if (jobs.length === 0) {
    return (
      <p className="text-body text-ink-muted">
        No runs yet. Choose a company, build a decision and press Run in the{" "}
        <Link href="/decisions" className="text-mint underline underline-offset-4">
          Decision Builder
        </Link>
        .
      </p>
    );
  }
  return (
    <ul className="flex flex-col divide-y divide-line rounded-panel border border-line bg-surface">
      {jobs.map((job) => (
        <li
          key={job.job_id}
          className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
        >
          {job.status === "completed" ? (
            <Link href={`/run?job=${job.job_id}`} className="font-medium text-ink hover:text-mint">
              {job.request.decision.type.replaceAll("_", " ")}, {job.request.case_id}
            </Link>
          ) : (
            <span className="text-ink">{job.request.case_id}</span>
          )}
          <Badge tone={STATUS_TONES[job.status]}>{STATUS_LABELS[job.status]}</Badge>
        </li>
      ))}
    </ul>
  );
}
