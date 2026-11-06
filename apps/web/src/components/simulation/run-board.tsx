"use client";

import type { JobEstimate, SimulationRequest } from "@multiverse/contracts";
import { useCallback, useEffect, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ACTION_LABELS,
  POLL_MS,
  STATUS_LABELS,
  STATUS_TONES,
  act,
  actionsFor,
  estimateRun,
  fetchJobs,
  formatDuration,
  isSimulation,
  submitRun,
  type JobAction,
  type SimulationJob,
} from "@/models/jobs";

const PATHS = [500, 1000, 3000, 10000];
const MAX_RUNTIME_SECONDS = 900;

type Choice = SimulationRequest["decision"];
type Board =
  { state: "loading" } | { state: "offline" } | { state: "ready"; jobs: SimulationJob[] };

function requestFor(caseId: string, decision: Choice, paths: number, seed: number) {
  const request: SimulationRequest = {
    kind: "simulation",
    idempotency_key: `launch-${paths}-${seed}`,
    owner: "owner",
    case_id: caseId,
    decision,
    settings: {
      paths,
      seed,
      batch_paths: 250,
      max_redraws: 3,
      lock_macro: false,
      shock_scale: 1,
      mean_block_quarters: null,
    },
    max_runtime_seconds: MAX_RUNTIME_SECONDS,
    spend_limit_usd: 0,
    rate_usd_per_hour: 0,
    overnight: false,
  };
  return request;
}

function RunRow({ job, onAct }: { job: SimulationJob; onAct: (id: string, a: JobAction) => void }) {
  const percent = Math.round(job.progress_percent);
  return (
    <li className="flex flex-col gap-2 rounded-panel border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-small font-medium text-ink">
          {job.request.settings.paths} paths, seed {job.request.settings.seed}
        </span>
        <Badge tone={STATUS_TONES[job.status]}>{STATUS_LABELS[job.status]}</Badge>
      </div>
      <div
        role="progressbar"
        aria-label={`Progress of run ${job.job_id}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 overflow-hidden rounded-pill bg-inset"
      >
        <div className="h-full rounded-pill bg-mint" style={{ width: `${percent}%` }} />
      </div>
      <p className="text-small text-ink-muted tabular-nums">
        {percent}%, {formatDuration(job.elapsed_seconds)}
        {job.reason ? `. ${job.reason}` : ""}
      </p>
      <div className="flex flex-wrap gap-2">
        {actionsFor(job).map((action) => (
          <Button key={action} variant="secondary" onClick={() => onAct(job.job_id, action)}>
            {ACTION_LABELS[action]}
          </Button>
        ))}
      </div>
    </li>
  );
}

/** Starts a run of this case through the queue: the page never computes a path. */
export function RunBoard({ caseId, decision }: { caseId: string; decision: Choice }) {
  const [board, setBoard] = useState<Board>({ state: "loading" });
  const [paths, setPaths] = useState(1000);
  const [seed, setSeed] = useState(20261106);
  const [estimate, setEstimate] = useState<JobEstimate | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const jobs = await fetchJobs(signal);
      setBoard({ state: "ready", jobs: jobs.filter(isSimulation) });
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

  const run = async (work: () => Promise<unknown>) => {
    setProblem(null);
    try {
      await work();
      await refresh();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The service did not answer.");
    }
  };

  if (board.state === "loading")
    return <p className="text-small text-ink-muted">Checking the service.</p>;
  if (board.state === "offline") {
    return (
      <Alert tone="info" title="The service is not running">
        A run needs the API and a worker on this computer. Everything above comes from the stored
        report and does not need them.
      </Alert>
    );
  }
  const request = requestFor(caseId, decision, paths, seed);
  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-wrap items-end gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void run(async () => setEstimate(await estimateRun(request)));
        }}
      >
        <label className="flex flex-col gap-1 text-small text-ink">
          Paths
          <select
            className="min-h-12 rounded-control border border-line-strong bg-surface px-3"
            value={paths}
            onChange={(event) => {
              setPaths(Number(event.target.value));
              setEstimate(null);
            }}
          >
            {PATHS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-small text-ink">
          Seed
          <input
            className="min-h-12 w-40 rounded-control border border-line-strong bg-surface px-3"
            type="number"
            min={0}
            value={seed}
            onChange={(event) => {
              setSeed(Number(event.target.value));
              setEstimate(null);
            }}
          />
        </label>
        <Button type="submit" variant="secondary">
          Estimate
        </Button>
        {estimate ? (
          <Button type="button" onClick={() => void run(() => submitRun(request))}>
            Queue this run
          </Button>
        ) : null}
      </form>
      {estimate ? (
        <p className="text-small text-ink-muted">
          About {formatDuration(estimate.seconds)} on the CPU, {estimate.disk_mb} MB of disk,{" "}
          {estimate.cost_usd} USD. {estimate.basis}.
        </p>
      ) : null}
      {problem ? (
        <Alert tone="negative" title="The request failed">
          {problem}
        </Alert>
      ) : null}
      {board.jobs.length ? (
        <ul className="flex flex-col gap-3" aria-label="Runs">
          {board.jobs.map((job) => (
            <RunRow
              key={job.job_id}
              job={job}
              onAct={(id, action) => void run(() => act(id, action))}
            />
          ))}
        </ul>
      ) : (
        <p className="text-small text-ink-muted">No run yet.</p>
      )}
    </div>
  );
}
