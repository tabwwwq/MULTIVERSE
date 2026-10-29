"use client";

import type { ScenarioDraft } from "@multiverse/contracts";
import { BookmarkPlus, X } from "lucide-react";
import Link from "next/link";
import { useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { CONTROL, TextField } from "@/components/ui/field";
import { addRevision, createScenario, findScenario, metaIssues, parseTags } from "@/notebook/model";
import { useNotebook } from "@/notebook/use-notebook";
import { cn } from "@/lib/cn";

export interface SavedTarget {
  scenarioId: string;
  /** The revision the form was restored from or last saved as: the parent of the next one. */
  revision: number;
  name: string;
}

interface SaveToNotebookProps {
  draft: ScenarioDraft | null;
  blockedReason: string | null;
  defaultName: string;
  target: SavedTarget | null;
  onSaved: (target: SavedTarget) => void;
}

const STATUS_TEXT = {
  quota:
    "This device's storage is full, so the scenario is kept only until you close the tab. Export the notebook as JSON to keep it.",
  unavailable:
    "This browser does not allow storage here (for example in private mode), so the scenario is kept only until you close the tab. Export the notebook as JSON to keep it.",
  corrupt:
    "Saved data on this device cannot be read, so nothing new is written over it. Open the notebook to download or reset it.",
} as const;

/*
 * Saves a validated decision (PRD FR-LB-01): a new scenario, or the next revision of the
 * scenario the form came from. Earlier revisions never change. Storage is this device
 * only, and the dialog says so.
 */
export function SaveToNotebook({
  draft,
  blockedReason,
  defaultName,
  target,
  onSaved,
}: SaveToNotebookProps) {
  const notebook = useNotebook();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const reasonId = useId();
  const [name, setName] = useState(defaultName);
  const [tags, setTags] = useState("");
  const [notes, setNotes] = useState("");
  const [asRevision, setAsRevision] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [outcome, setOutcome] = useState<{ text: string; scenarioId: string; ok: boolean } | null>(
    null,
  );

  const existing = target ? findScenario(notebook.notebook, target.scenarioId) : undefined;
  const revisionOf = existing && asRevision ? existing : undefined;

  const open = () => {
    setName(existing?.name ?? defaultName);
    setTags(existing?.tags.join(", ") ?? "");
    setNotes(existing?.notes ?? "");
    setErrors([]);
    dialogRef.current?.showModal();
  };

  const submit = () => {
    if (!draft) return;
    let next;
    let saved: SavedTarget;
    if (revisionOf && target) {
      const added = addRevision(notebook.notebook, revisionOf.scenario_id, draft, target.revision);
      next = added.notebook;
      saved = {
        scenarioId: revisionOf.scenario_id,
        revision: added.ref.revision,
        name: revisionOf.name,
      };
    } else {
      const meta = { name, tags: parseTags(tags), notes };
      const issues = metaIssues(meta);
      if (issues.length > 0) {
        setErrors(issues);
        return;
      }
      const created = createScenario(notebook.notebook, draft, meta);
      next = created.notebook;
      saved = { scenarioId: created.ref.scenario_id, revision: 1, name: meta.name.trim() };
    }
    const result = notebook.save(next);
    onSaved(saved);
    setOutcome({
      ok: result.ok,
      scenarioId: saved.scenarioId,
      text: result.ok
        ? `Saved as revision ${saved.revision} of “${saved.name}”, on this device only.`
        : STATUS_TEXT[result.status],
    });
    dialogRef.current?.close();
  };

  return (
    <>
      <Button
        variant="secondary"
        disabled={blockedReason !== null || !notebook.ready}
        aria-describedby={blockedReason ? reasonId : undefined}
        onClick={open}
      >
        <BookmarkPlus aria-hidden="true" />
        Save to notebook
      </Button>
      {blockedReason ? (
        <span id={reasonId} className="sr-only">
          Save needs a checked decision: {blockedReason}
        </span>
      ) : null}
      {outcome ? (
        <p
          role="status"
          className={cn("basis-full text-small", outcome.ok ? "text-mint" : "text-warning")}
        >
          {outcome.text}{" "}
          <Link
            href={`/notebook?scenario=${outcome.scenarioId}`}
            className="text-ink underline underline-offset-4"
          >
            Open in notebook
          </Link>
        </p>
      ) : null}
      <dialog ref={dialogRef} aria-labelledby={titleId} {...{ closedby: "any" }} className="modal">
        <form
          method="dialog"
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <div className="flex items-start justify-between gap-4">
            <h2 id={titleId} className="font-display text-h4 text-ink">
              Save to notebook
            </h2>
            <button
              type="button"
              aria-label="Close"
              onClick={() => dialogRef.current?.close()}
              className="-m-2 rounded-control p-2 text-ink-muted hover:bg-inset hover:text-ink"
            >
              <X aria-hidden="true" className="size-5" />
            </button>
          </div>
          <p className="text-small text-ink-muted">
            Only on this device: the notebook lives in this browser. Export it as JSON to keep a
            copy.
          </p>
          {existing ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="text-small font-medium text-ink">Save as</legend>
              <label className="flex items-start gap-3 text-body text-ink">
                <input
                  type="radio"
                  name="save-as"
                  checked={asRevision}
                  onChange={() => setAsRevision(true)}
                  className="mt-1 size-5 accent-mint"
                />
                <span>
                  Revision {existing.revisions.length + 1} of “{existing.name}”
                  <span className="block text-small text-ink-muted">
                    Revision {target?.revision} stays as it is.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-3 text-body text-ink">
                <input
                  type="radio"
                  name="save-as"
                  checked={!asRevision}
                  onChange={() => setAsRevision(false)}
                  className="mt-1 size-5 accent-mint"
                />
                A new scenario
              </label>
            </fieldset>
          ) : null}
          {revisionOf ? null : (
            <>
              <TextField
                id="save-name"
                label="Name"
                required
                value={name}
                maxLength={120}
                onChange={(event) => setName(event.target.value)}
              />
              <TextField
                id="save-tags"
                label="Tags"
                hint="Separated by commas, for example rnd, northwind."
                value={tags}
                onChange={(event) => setTags(event.target.value)}
              />
              <div className="flex flex-col gap-1.5">
                <label htmlFor="save-notes" className="text-small font-medium text-ink">
                  Notes
                </label>
                <textarea
                  id="save-notes"
                  value={notes}
                  maxLength={5000}
                  rows={4}
                  onChange={(event) => setNotes(event.target.value)}
                  className={cn(CONTROL, "py-2")}
                />
              </div>
            </>
          )}
          {errors.length > 0 ? (
            <ul role="alert" className="text-small text-negative">
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          ) : null}
          <div className="flex flex-wrap justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => dialogRef.current?.close()}>
              Cancel
            </Button>
            <Button type="submit">Save</Button>
          </div>
        </form>
      </dialog>
    </>
  );
}
