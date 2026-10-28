"use client";

import type { ScenarioDraft } from "@multiverse/contracts";
import { Download, X } from "lucide-react";
import { useId, useRef } from "react";
import { Button } from "@/components/ui/button";

interface RunDialogProps {
  draft: ScenarioDraft | null;
  /** Why Run is not available, or null when it is. */
  blockedReason: string | null;
}

/*
 * Runs arrive in Stage 06. Until then Run is enabled only for a fresh, valid decision
 * (US-05) and shows the exact scenario JSON a run will receive, in a native modal dialog.
 */
export function RunDialog({ draft, blockedReason }: RunDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const reasonId = useId();
  const json = draft ? `${JSON.stringify(draft, null, 2)}\n` : "";

  const download = () => {
    if (!draft) return;
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `scenario-${draft.decision.type}-${draft.as_of}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

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
          <p className="text-body text-ink-muted">
            The simulation engine is not built yet: demo runs arrive in Stage 06. This decision
            passed validation, and this is the scenario a run will receive.
          </p>
          <pre
            tabIndex={0}
            aria-label="Scenario JSON"
            className="max-h-80 overflow-auto rounded-control border border-line bg-inset p-3 text-small whitespace-pre-wrap text-ink [overflow-wrap:anywhere]"
          >
            {json}
          </pre>
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="secondary" onClick={download}>
              <Download aria-hidden="true" />
              Download JSON
            </Button>
            <Button type="submit" value="close">
              Close
            </Button>
          </div>
        </form>
      </dialog>
    </>
  );
}
