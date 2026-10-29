"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { browserStorage, inventory, type StoredItem } from "@/notebook/storage";
import { useNotebook } from "@/notebook/use-notebook";

const DESCRIPTIONS: Record<string, string> = {
  "multiverse.notebook": "Research notebook: saved scenarios, revisions and exported reports.",
  "multiverse.sidebar.collapsed": "Whether the navigation sidebar is collapsed.",
};

function size(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

/*
 * What this prototype keeps in the browser, and a way to delete all of it (PRD FR-ST-02,
 * NFR-PRIV-01). Only keys of this app are listed or removed.
 */
export function PrivacySettings() {
  const notebook = useNotebook();
  const [, setVersion] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const items: StoredItem[] = notebook.ready ? inventory(browserStorage()) : [];

  if (!notebook.ready) return <p className="text-body text-ink-muted">Reading this device…</p>;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <section aria-labelledby="stored-title" className="flex flex-col gap-3">
        <h2 id="stored-title" className="font-display text-h3 text-ink">
          Stored on this device
        </h2>
        {notebook.status === "unavailable" ? (
          <p className="text-small text-warning">
            This browser does not allow storage here, so nothing is stored.
          </p>
        ) : null}
        {items.length === 0 ? (
          <p className="text-body text-ink-muted" data-testid="storage-empty">
            Nothing. This prototype keeps no data about you on this device.
          </p>
        ) : (
          <ul
            className="flex flex-col divide-y divide-line rounded-panel border border-line bg-surface"
            data-testid="storage-items"
          >
            {items.map((item) => (
              <li key={item.key} className="flex flex-col gap-0.5 px-4 py-3">
                <span className="flex flex-wrap justify-between gap-2 text-small text-ink">
                  <code>{item.key}</code>
                  <span className="tabular-nums text-ink-muted">{size(item.bytes)}</span>
                </span>
                <span className="text-small text-ink-muted">
                  {DESCRIPTIONS[item.key] ?? "Setting of this app."}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-small text-ink-muted">
          {notebook.notebook.scenarios.length} saved scenarios, {notebook.notebook.reports.length}{" "}
          exported reports.
        </p>
      </section>

      <section aria-labelledby="delete-all-title" className="flex flex-col gap-3">
        <h2 id="delete-all-title" className="font-display text-h3 text-ink">
          Delete everything
        </h2>
        <p className="text-body text-ink-muted">
          Removes the notebook, its reports and the display settings of this app from this browser.
          Other sites are not affected. Export the notebook first if you want a copy.
        </p>
        <div>
          <Modal
            title="Delete all MULTIVERSE data on this device?"
            description="Saved scenarios, revisions, reports and settings are removed from this browser. This cannot be undone."
            triggerLabel="Delete all data on this device"
            triggerVariant="danger"
            cancelLabel="Keep my data"
            confirmLabel="Delete everything"
            onClose={(result) => {
              if (result !== "confirm") return;
              const removed = notebook.reset();
              setVersion((value) => value + 1);
              setMessage(
                removed
                  ? "All MULTIVERSE data on this device was deleted."
                  : "Some data could not be deleted: this browser blocked access to storage.",
              );
            }}
          />
        </div>
        <p role="status" className="text-small text-mint empty:hidden">
          {message}
        </p>
      </section>

      <section aria-labelledby="privacy-title" className="flex flex-col gap-2">
        <h2 id="privacy-title" className="font-display text-h3 text-ink">
          Privacy
        </h2>
        <ul className="flex list-disc flex-col gap-1 pl-5 text-body text-ink-muted">
          <li>No accounts and no analytics in this version (decision D-07).</li>
          <li>Nothing you enter is sent to a server: scenarios stay in this browser.</li>
          <li>
            Display settings for amounts and number formats are planned with Gate A (Stage 08).
          </li>
        </ul>
      </section>
    </div>
  );
}
