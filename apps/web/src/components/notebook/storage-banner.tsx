"use client";

import { HardDrive } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { downloadText } from "@/lib/download";
import type { StorageStatus } from "@/notebook/storage";

interface StorageBannerProps {
  status: StorageStatus;
  unreadable: string | null;
  onReset: () => void;
}

/*
 * "Only on this device" (PRD FR-LB-01, SP-02), always visible, plus what to do when the
 * browser cannot store the notebook (FC-10). Unreadable data is offered for download
 * before it can be cleared.
 */
export function StorageBanner({ status, unreadable, onReset }: StorageBannerProps) {
  return (
    <div className="flex flex-col gap-3">
      <div
        className="flex items-start gap-3 rounded-panel border border-line bg-surface p-4"
        data-testid="device-only"
      >
        <HardDrive aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-blue" />
        <div className="flex flex-col gap-1">
          <p className="font-medium text-ink">Only on this device</p>
          <p className="text-small text-ink-muted">
            The notebook is saved in this browser, nowhere else. Another browser or device will not
            see it, and clearing site data deletes it. Export the notebook as JSON to keep a copy.
            Server storage arrives with accounts (Stage 24).
          </p>
        </div>
      </div>
      {status === "quota" ? (
        <Alert tone="warning" title="Storage on this device is full" live>
          The last change is kept until you close the tab, but it is not saved. Export the notebook
          as JSON, then delete scenarios you no longer need.
        </Alert>
      ) : null}
      {status === "unavailable" ? (
        <Alert tone="warning" title="This browser does not allow storage here" live>
          This happens in private windows or when site data is blocked. You can work, but nothing is
          saved after you close the tab. Export the notebook as JSON to keep your work.
        </Alert>
      ) : null}
      {status === "corrupt" ? (
        <Alert tone="negative" title="Saved data on this device cannot be read" live>
          <span className="flex flex-col gap-3">
            <span>
              It may come from another version or have been changed outside the app. Nothing is
              written over it until you decide.
            </span>
            <span className="flex flex-wrap gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  downloadText(
                    "multiverse_unreadable_notebook.json",
                    unreadable ?? "",
                    "application/json",
                  )
                }
              >
                Download the unreadable data
              </Button>
              <Modal
                title="Delete the unreadable data?"
                description="The notebook on this device starts empty. Download the data first if you may need it."
                triggerLabel="Start an empty notebook"
                triggerVariant="danger"
                cancelLabel="Keep it"
                confirmLabel="Delete and start empty"
                onClose={(result) => {
                  if (result === "confirm") onReset();
                }}
              />
            </span>
          </span>
        </Alert>
      ) : null}
    </div>
  );
}
