"use client";

import type { JobLogLine } from "@multiverse/contracts";
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
  fetchLogs,
  formatDuration,
  silentFor,
  isTraining,
  type JobAction,
  type TrainingJob,
} from "@/models/jobs";

type Board = { state: "loading" } | { state: "offline" } | { state: "ready"; jobs: TrainingJob[] };

function ProgressBar({ job }: { job: TrainingJob }) {
  const percent = Math.round(job.progress_percent);
  return (
    <div className="flex items-center gap-3">
      <div
        role="progressbar"
        aria-label={`Training progress of ${job.job_id}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 min-w-0 flex-1 overflow-hidden rounded-pill bg-inset"
      >
        <div className="h-full rounded-pill bg-mint" style={{ width: `${percent}%` }} />
      </div>
      <span className="text-small font-medium text-ink tabular-nums">{percent}%</span>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-micro text-ink-muted">{label}</dt>
      <dd className="text-small text-ink tabular-nums">{value}</dd>
    </div>
  );
}

function JobLog({ jobId }: { jobId: string }) {
  const [lines, setLines] = useState<JobLogLine[] | null>(null);
  return (
    <details
      onToggle={(event) => {
        if (event.currentTarget.open) {
          fetchLogs(jobId)
            .then(setLines)
            .catch(() => setLines([]));
        }
      }}
    >
      <summary className="cursor-pointer text-small text-ink-muted">Log</summary>
      {lines === null ? (
        <p className="mt-2 text-small text-ink-muted">Reading the log…</p>
      ) : (
        <ol className="mt-2 flex max-h-64 flex-col gap-1 overflow-y-auto font-mono text-micro text-ink-muted">
          {lines.map((line) => (
            <li key={line.seq}>{line.message}</li>
          ))}
        </ol>
      )}
    </details>
  );
}

interface JobCardProps {
  job: TrainingJob;
  now: number;
  onAction: (jobId: string, action: JobAction) => void;
  busy: boolean;
}

function JobCard({ job, now, onAction, busy }: JobCardProps) {
  const { request, estimate } = job;
  const silent = silentFor(job, now);
  const spend =
    request.rate_usd_per_hour > 0
      ? `${job.spent_usd.toFixed(2)} of ${request.spend_limit_usd} USD`
      : "Own hardware, 0 USD";
  return (
    <li className="flex flex-col gap-4 rounded-panel border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-medium text-ink">
            {request.model}, fold {request.fold_year}
          </h3>
          <p className="truncate font-mono text-micro text-ink-muted">{job.job_id}</p>
        </div>
        <Badge tone={STATUS_TONES[job.status]}>{STATUS_LABELS[job.status]}</Badge>
      </div>
      <ProgressBar job={job} />
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-4">
        <Fact label="Epoch" value={`${job.epoch} of ${request.max_epochs}`} />
        <Fact
          label="Best epoch"
          value={job.best_epoch === null ? "None yet" : `${job.best_epoch}`}
        />
        <Fact
          label="Validation loss"
          value={job.validation_loss === null ? "None yet" : job.validation_loss.toFixed(4)}
        />
        <Fact label="Elapsed" value={formatDuration(job.elapsed_seconds)} />
        <Fact label="Runtime limit" value={formatDuration(request.max_runtime_seconds)} />
        <Fact label="Spend" value={spend} />
        <Fact label="Attempt" value={`${job.attempt} of ${job.max_attempts}`} />
        <Fact label="Batch" value={`${job.batch_size}`} />
      </dl>
      {!job.approved_at ? (
        <Alert tone="info" title="Waiting for approval">
          Estimate: {formatDuration(estimate.seconds)}, {estimate.vram_mb} MB of GPU memory,{" "}
          {estimate.disk_mb} MB on disk, {estimate.cost_usd} USD. {estimate.basis}.
        </Alert>
      ) : null}
      {silent !== null && silent > STALE_SECONDS ? (
        <Alert tone="warning" title={`No heartbeat for ${formatDuration(silent)}`}>
          The worker may have died. When its lease ends, the next worker goes on from the last
          checkpoint.
        </Alert>
      ) : null}
      {job.reason ? <p className="text-small text-ink-muted">{job.reason}</p> : null}
      {job.alerts.map((alert) => (
        <Alert key={alert} tone="negative" title="Alert">
          {alert}
        </Alert>
      ))}
      {actionsFor(job).length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {actionsFor(job).map((action) => (
            <Button
              key={action}
              size="sm"
              variant={action === "stop" ? "danger" : "secondary"}
              disabled={busy}
              onClick={() => onAction(job.job_id, action)}
            >
              {ACTION_LABELS[action]}
            </Button>
          ))}
        </div>
      ) : null}
      <JobLog jobId={job.job_id} />
    </li>
  );
}

/*
 * The live state of the training jobs. The worker owns it: this page reads it every two
 * seconds and passes on requests, so the browser may close without touching a job.
 */
export function JobBoard() {
  const [board, setBoard] = useState<Board>({ state: "loading" });
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const jobs = await fetchJobs(signal);
      setBoard({ state: "ready", jobs: jobs.filter(isTraining) });
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
          setProblem(error instanceof Error ? error.message : "The request failed"),
        )
        .finally(() => {
          setBusy(false);
          void refresh();
        });
    },
    [refresh],
  );

  if (board.state === "loading") {
    return <p className="text-body text-ink-muted">Reading the job queue…</p>;
  }
  if (board.state === "offline") {
    return (
      <Alert tone="info" title="The job service is not running" live>
        This page shows real jobs only, so it shows none now. Start it with{" "}
        <code>npm run dev:api</code>. Jobs do not depend on this page: their state is on disk.
      </Alert>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {problem ? (
        <Alert tone="negative" title="The request was refused" live>
          {problem}
        </Alert>
      ) : null}
      {board.jobs.length === 0 ? (
        <p className="text-body text-ink-muted">No training jobs yet.</p>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {board.jobs.map((job) => (
            <JobCard key={job.job_id} job={job} now={now} onAction={onAction} busy={busy} />
          ))}
        </ul>
      )}
      <p className="text-small text-ink-muted">
        Progress counts epochs against the maximum; early stopping jumps to 100%. Stop and pause
        wait for a safe point. A forced kill (<code>multiverse-worker kill</code>) loses the running
        epoch.
      </p>
    </div>
  );
}
