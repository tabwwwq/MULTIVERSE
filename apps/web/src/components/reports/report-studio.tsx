"use client";

import type { ResearchReport, SimulationReport } from "@multiverse/contracts";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ReportView } from "@/components/reports/report-view";
import { RunSummary } from "@/components/simulation/run-summary";
import { Alert } from "@/components/ui/alert";
import {
  fetchDocument,
  fetchJobs,
  fetchReport,
  isSimulation,
  type SimulationJob,
} from "@/models/jobs";

type Load =
  | { state: "loading" }
  | { state: "ready"; report: ResearchReport; run: SimulationReport | null }
  | { state: "failed"; message: string };

const JOB = /^job-[0-9a-f]{12}$/;

function RunList() {
  const [jobs, setJobs] = useState<SimulationJob[] | null | "offline">(null);
  useEffect(() => {
    const controller = new AbortController();
    fetchJobs(controller.signal)
      .then((found) =>
        setJobs(found.filter(isSimulation).filter((job) => job.status === "completed")),
      )
      .catch(() => {
        if (!controller.signal.aborted) setJobs("offline");
      });
    return () => controller.abort();
  }, []);
  if (jobs === null) return <p className="text-body text-ink-muted">Reading the runs.</p>;
  if (jobs === "offline") {
    return (
      <Alert tone="info" title="Reports live with the engine on this computer">
        Start it with <code>npm run app</code>. The case studies of Stage 25 are in{" "}
        <code>docs/case-studies</code> of the repository.
      </Alert>
    );
  }
  if (jobs.length === 0) {
    return (
      <p className="text-body text-ink-muted">
        No finished run yet. Build a decision and press Run in the{" "}
        <Link href="/decisions" className="text-mint underline underline-offset-4">
          Decision Builder
        </Link>
        .
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {jobs.map((job) => (
        <li key={job.job_id}>
          <Link
            href={`/reports?job=${job.job_id}`}
            className="text-mint underline underline-offset-4"
          >
            Report of {job.job_id}
          </Link>{" "}
          <span className="text-small text-ink-muted">
            {job.request.case_id}, {job.request.decision.type.replaceAll("_", " ")},{" "}
            {job.request.settings.paths.toLocaleString("en-US")} paths
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The list of local runs, or the report of one of them. */
export function ReportStudio() {
  const job = useSearchParams().get("job");
  const valid = job !== null && JOB.test(job);
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    if (!valid || !job) return undefined;
    const controller = new AbortController();
    Promise.all([
      fetchDocument(job, controller.signal),
      fetchReport(job, controller.signal).catch(() => null),
    ])
      .then(([report, run]) =>
        setLoad({ state: "ready", report, run: Array.isArray(run?.values) ? run : null }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : "The service did not answer.";
        setLoad({ state: "failed", message });
      });
    return () => controller.abort();
  }, [job, valid]);

  if (!valid || !job) return <RunList />;
  if (load.state === "loading")
    return <p className="text-body text-ink-muted">Reading the report.</p>;
  if (load.state === "failed") {
    return (
      <Alert tone="warning" title="This report cannot be read">
        {load.message} Reports live on this computer: start the engine with <code>npm run app</code>
        . A run finished before Stage 25 gets its report with <code>multiverse-worker reports</code>
        .
      </Alert>
    );
  }
  return (
    <div className="flex flex-col gap-10">
      {load.run ? <RunSummary report={load.run} /> : null}
      <ReportView report={load.report} jobId={job} onPrint={() => window.print()} />
    </div>
  );
}
