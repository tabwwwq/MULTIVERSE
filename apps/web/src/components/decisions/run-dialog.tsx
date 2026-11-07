"use client";

import type { JobView, ScenarioDraft, SimulationRequest } from "@multiverse/contracts";
import { Download, Play, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { act, estimateRun, fetchJob, submitRun } from "@/models/jobs";

export interface RunTarget {
  /** The case of this company, or null when no run can start from it. */
  caseId: string | null;
  /** Why not, in the words of the export. */
  note: string | null;
}

interface RunDialogProps {
  draft: ScenarioDraft | null;
  /** Why Run is not available, or null when it is. */
  blockedReason: string | null;
  target: RunTarget;
}

const PATHS = [500, 1000, 3000];
const POLL_MS = 700;
const SECONDS_PER_PATH = 0.02;
const FLOOR_SECONDS = 120;

type Phase =
  | { name: "idle" }
  | { name: "starting" }
  | { name: "running"; job: JobView }
  | { name: "failed"; message: string }
  | { name: "offline" };

function requestFor(caseId: string, draft: ScenarioDraft, paths: number): SimulationRequest {
  return {
    kind: "simulation",
    idempotency_key: `run-${crypto.randomUUID()}`,
    owner: "owner",
    case_id: caseId,
    decision: draft.decision,
    settings: {
      paths,
      seed: draft.seed,
      batch_paths: 250,
      max_redraws: 3,
      lock_macro: false,
      shock_scale: 1,
      mean_block_quarters: null,
    },
    max_runtime_seconds: Math.ceil(FLOOR_SECONDS + paths * SECONDS_PER_PATH),
    spend_limit_usd: 0,
    rate_usd_per_hour: 0,
    overnight: false,
  };
}

/*
 * A run of a real company goes through the job queue: the API records it, the worker computes it,
 * the screen only watches. Pressing Run is the approval of its estimate, which is free compute on
 * this machine. A fictional company has no case, so its dialog shows the scenario JSON instead.
 */
export function RunDialog({ draft, blockedReason, target }: RunDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const router = useRouter();
  const titleId = useId();
  const reasonId = useId();
  const [paths, setPaths] = useState(1000);
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const json = draft ? `${JSON.stringify(draft, null, 2)}\n` : "";
  const running = phase.name === "running" ? phase.job.job_id : null;

  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => {
      void fetchJob(running)
        .then((job) => {
          if (job.status === "completed") {
            window.clearInterval(timer);
            router.push(`/run?job=${job.job_id}`);
          } else if (job.status === "failed" || job.status === "stopped") {
            window.clearInterval(timer);
            setPhase({ name: "failed", message: job.reason ?? "The run did not finish." });
          } else {
            setPhase({ name: "running", job });
          }
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [router, running]);

  const start = async () => {
    if (!draft || !target.caseId) return;
    setPhase({ name: "starting" });
    const request = requestFor(target.caseId, draft, paths);
    try {
      await estimateRun(request);
    } catch {
      setPhase({ name: "offline" });
      return;
    }
    try {
      const job = await submitRun(request);
      setPhase({ name: "running", job: await act(job.job_id, "approve") });
    } catch (error) {
      const message = error instanceof Error ? error.message : "The service did not answer.";
      setPhase({ name: "failed", message });
    }
  };

  const download = () => {
    if (!draft) return;
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `scenario-${draft.decision.type}-${draft.as_of}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const percent = phase.name === "running" ? Math.round(phase.job.progress_percent) : 0;
  const busy = phase.name === "starting" || phase.name === "running";

  return (
    <>
      <Button
        disabled={blockedReason !== null}
        aria-describedby={blockedReason ? reasonId : undefined}
        onClick={() => dialogRef.current?.showModal()}
      >
        Run
      </Button>
      {blockedReason ? (
        <p id={reasonId} className="basis-full text-small text-ink-muted">
          {blockedReason}
        </p>
      ) : null}
      <dialog ref={dialogRef} aria-labelledby={titleId} {...{ closedby: "any" }} className="modal">
        <form method="dialog" className="flex flex-col gap-5">
          <div className="flex items-start justify-between gap-4">
            <h2 id={titleId} className="font-display text-h4 text-ink">
              Ready to run
            </h2>
            <button
              value="dismissed"
              aria-label="Close"
              className="-m-2 rounded-control p-2 text-ink-muted hover:bg-inset hover:text-ink"
            >
              <X aria-hidden="true" className="size-5" />
            </button>
          </div>

          {target.caseId ? (
            <>
              <p className="text-body text-ink-muted">
                This runs paired Monte Carlo paths of the company with and without this decision,
                through the three statements, on this computer. Results are conditional on the
                assumed model and are not advice. Macro shocks come from U.S. Treasury yields and
                World Bank GDP growth (CC BY 4.0).
              </p>
              {target.note ? (
                <Alert tone="warning" title="This case stands on a substitute">
                  {target.note}
                </Alert>
              ) : null}
              <fieldset className="flex flex-wrap items-center gap-3" disabled={busy}>
                <legend className="mb-2 text-small text-ink-muted">Paths</legend>
                {PATHS.map((count) => (
                  <label key={count} className="flex items-center gap-2 text-small text-ink">
                    <input
                      type="radio"
                      name="paths"
                      checked={paths === count}
                      onChange={() => setPaths(count)}
                    />
                    {count.toLocaleString("en-US")}
                  </label>
                ))}
              </fieldset>
              {phase.name === "running" ? (
                <div
                  role="progressbar"
                  aria-label="Progress of the run"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={percent}
                  className="h-2 overflow-hidden rounded-full bg-inset"
                >
                  <div className="h-full bg-mint" style={{ width: `${percent}%` }} />
                </div>
              ) : null}
              {phase.name === "offline" ? (
                <Alert tone="warning" title="The engine is not running on this computer">
                  Start it with <code>npm run app</code> in the project folder, then press Run
                  again.
                </Alert>
              ) : null}
              {phase.name === "failed" ? (
                <Alert tone="negative" title="The run did not finish">
                  {phase.message}
                </Alert>
              ) : null}
            </>
          ) : (
            <p className="text-body text-ink-muted">
              {target.note ?? "This company has no case to run."} The scenario below passed
              validation. Examples of results are in the{" "}
              <Link href="/timeline" className="text-mint underline underline-offset-4">
                Timeline Explorer
              </Link>
              .
            </p>
          )}

          <details>
            <summary className="cursor-pointer text-small text-ink-muted">Scenario JSON</summary>
            <pre
              tabIndex={0}
              aria-label="Scenario JSON"
              className="mt-2 max-h-60 overflow-auto rounded-control border border-line bg-inset p-3 text-small whitespace-pre-wrap text-ink [overflow-wrap:anywhere]"
            >
              {json}
            </pre>
          </details>
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="secondary" onClick={download}>
              <Download aria-hidden="true" />
              Download JSON
            </Button>
            {target.caseId ? (
              <Button disabled={busy} onClick={() => void start()}>
                <Play aria-hidden="true" />
                {busy ? `Running ${percent}%` : "Run simulation"}
              </Button>
            ) : (
              <Button type="submit" value="close">
                Close
              </Button>
            )}
          </div>
        </form>
      </dialog>
    </>
  );
}
