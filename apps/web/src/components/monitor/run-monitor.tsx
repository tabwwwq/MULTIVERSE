"use client";

import type { JobStatus } from "@multiverse/contracts";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ACTION_LABELS,
  POLL_MS,
  STALE_SECONDS,
  STATUS_LABELS,
  STATUS_TONES,
  act,
  actionsFor,
  fetchJobs,
  formatDuration,
  isSimulation,
  isTraining,
  silentFor,
  type JobAction,
  type SimulationJob,
} from "@/models/jobs";

const DECISIONS: Record<string, string> = {
  rnd_change: "R&D budget change",
  workforce_restructure: "Workforce restructuring",
  acquisition: "Acquisition",
  divestiture: "Divestiture or segment exit",
  capex_expansion: "CAPEX expansion",
  debt_refinance: "Debt refinancing",
};

const GROUPS: { label: string; statuses: JobStatus[]; tone: string }[] = [
  {
    label: "Running",
    statuses: ["validating", "running", "pause_requested", "stop_requested"],
    tone: "bg-blue",
  },
  { label: "Waiting", statuses: ["queued", "paused"], tone: "bg-violet" },
  { label: "Finished", statuses: ["completed"], tone: "bg-mint" },
  { label: "Stopped or failed", statuses: ["stopped", "failed"], tone: "bg-negative" },
];

type Board =
  | { state: "loading" }
  | { state: "offline" }
  | { state: "ready"; runs: SimulationJob[]; training: number };

interface RunMonitorProps {
  /** Company name by CIK without leading zeros, as a case id carries it. */
  names: Record<string, string>;
}

function companyOf(caseId: string, names: Record<string, string>): string {
  const cik = caseId.replace(/^case-/, "").replace(/-\d{8}$/, "");
  return names[cik] ?? (cik === "synthetic-northwind" ? "Northwind Precision (synthetic)" : caseId);
}

function Progress({ job }: { job: SimulationJob }) {
  const percent = Math.round(job.progress_percent);
  return (
    <div className="flex items-center gap-3">
      <div
        role="progressbar"
        aria-label={`Progress of ${job.job_id}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 min-w-24 flex-1 overflow-hidden rounded-pill bg-inset"
      >
        <div
          className={`h-full rounded-pill ${job.status === "completed" ? "bg-mint" : job.status === "failed" || job.status === "stopped" ? "bg-negative" : "bg-blue"}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="w-10 text-right text-small font-medium text-ink tabular-nums">
        {percent}%
      </span>
    </div>
  );
}

/** Every Monte Carlo run of this computer, live: the worker owns them, this page only watches. */
export function RunMonitor({ names }: RunMonitorProps) {
  const [board, setBoard] = useState<Board>({ state: "loading" });
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const jobs = await fetchJobs(signal);
      setBoard({
        state: "ready",
        runs: jobs.filter(isSimulation),
        training: jobs.filter(isTraining).length,
      });
      setNow(Date.now());
    } catch {
      if (!signal?.aborted) setBoard({ state: "offline" });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const first = window.setTimeout(() => void refresh(controller.signal), 0);
    const timer = window.setInterval(() => void refresh(controller.signal), POLL_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
      controller.abort();
    };
  }, [refresh]);

  const onAction = useCallback(
    (jobId: string, action: JobAction) => {
      setBusy(true);
      setProblem(null);
      act(jobId, action)
        .catch((error: unknown) =>
          setProblem(error instanceof Error ? error.message : "The request was refused."),
        )
        .finally(() => {
          setBusy(false);
          void refresh();
        });
    },
    [refresh],
  );

  if (board.state === "loading") {
    return <p className="text-body text-ink-muted">Reading the job queue.</p>;
  }
  if (board.state === "offline") {
    return (
      <Alert tone="info" title="The engine is not running on this computer" live>
        Runs live with the engine: start it with <code>npm run app</code> in the project folder.
        Nothing is lost while it is off: every run is on disk with its last checkpoint.
      </Alert>
    );
  }

  const runs = [...board.runs].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const total = runs.length;
  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="monitor-summary" className="flex flex-col gap-4">
        <h2 id="monitor-summary" className="sr-only">
          Runs by state
        </h2>
        <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {GROUPS.map((group) => {
            const count = runs.filter((run) => group.statuses.includes(run.status)).length;
            return (
              <div
                key={group.label}
                className="flex flex-col gap-1 rounded-panel border border-line bg-surface p-4"
              >
                <dt className="flex items-center gap-2 text-small text-ink-muted">
                  <span
                    aria-hidden="true"
                    className={`inline-block size-2.5 rounded-full ${group.tone}`}
                  />
                  {group.label}
                </dt>
                <dd className="font-display text-h3 text-ink tabular-nums">{count}</dd>
              </div>
            );
          })}
        </dl>
        {total > 0 ? (
          <div aria-hidden="true" className="flex h-2 overflow-hidden rounded-pill bg-inset">
            {GROUPS.map((group) => {
              const count = runs.filter((run) => group.statuses.includes(run.status)).length;
              return count ? (
                <div
                  key={group.label}
                  className={group.tone}
                  style={{ width: `${(100 * count) / total}%` }}
                />
              ) : null;
            })}
          </div>
        ) : null}
      </section>

      {problem ? (
        <Alert tone="negative" title="The request was refused" live>
          {problem}
        </Alert>
      ) : null}

      {total === 0 ? (
        <p className="max-w-prose text-body text-ink-muted">
          No runs yet. Build a decision in the{" "}
          <Link href="/decisions" className="text-mint underline underline-offset-4">
            Decision Builder
          </Link>{" "}
          and press Run: the run appears here and keeps going when this page closes.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {runs.map((run) => {
            const silent = silentFor(run, now);
            const actions = actionsFor(run);
            return (
              <li
                key={run.job_id}
                className="grid gap-4 rounded-panel border border-line bg-surface p-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)_auto] md:items-center"
              >
                <div className="min-w-0">
                  <h3 className="truncate font-medium text-ink">
                    {companyOf(run.request.case_id, names)}
                  </h3>
                  <p className="text-small text-ink-muted">
                    {DECISIONS[run.request.decision.type] ?? run.request.decision.type},{" "}
                    {run.request.settings.paths.toLocaleString("en-US")} paths
                  </p>
                  <p className="truncate font-mono text-micro text-ink-muted">{run.job_id}</p>
                </div>
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={STATUS_TONES[run.status]}>{STATUS_LABELS[run.status]}</Badge>
                    <span className="text-small text-ink-muted tabular-nums">
                      {formatDuration(run.elapsed_seconds)}
                    </span>
                    {silent !== null && silent > STALE_SECONDS ? (
                      <span className="text-small text-warning">
                        No heartbeat for {formatDuration(silent)}
                      </span>
                    ) : null}
                  </div>
                  <Progress job={run} />
                  {run.reason && run.status !== "completed" ? (
                    <p className="text-small text-ink-muted">{run.reason}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2 md:justify-end">
                  {run.status === "completed" ? (
                    <>
                      <Link
                        href={`/run?job=${run.job_id}`}
                        className="rounded-control border border-line px-3 py-2 text-small text-ink hover:border-line-strong"
                      >
                        Result
                      </Link>
                      <Link
                        href={`/reports?job=${run.job_id}`}
                        className="rounded-control border border-line px-3 py-2 text-small text-ink hover:border-line-strong"
                      >
                        Report
                      </Link>
                    </>
                  ) : null}
                  {actions.map((action) => (
                    <Button
                      key={action}
                      size="sm"
                      variant={action === "stop" ? "danger" : "secondary"}
                      disabled={busy}
                      onClick={() => onAction(run.job_id, action)}
                    >
                      {ACTION_LABELS[action]}
                    </Button>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {board.training > 0 ? (
        <p className="text-small text-ink-muted">
          {board.training} training {board.training === 1 ? "job is" : "jobs are"} on the{" "}
          <Link href="/models" className="text-mint underline underline-offset-4">
            Model Observatory
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}
