"use client";

import { Download, Lock, Upload } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { decisionSummary, ScenarioDetail } from "@/components/notebook/scenario-detail";
import { StorageBanner } from "@/components/notebook/storage-banner";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { CONTROL, SelectField } from "@/components/ui/field";
import { cn } from "@/lib/cn";
import { downloadText } from "@/lib/download";
import { mergeNotebook, parseNotebookFile } from "@/notebook/import";
import {
  addReport,
  allTags,
  type CompanyNames,
  deleteScenario,
  duplicateRevision,
  findScenario,
  latestRevision,
  type Notebook,
  searchScenarios,
  SYSTEM_CLOCK,
  updateMeta,
} from "@/notebook/model";
import { buildReport } from "@/notebook/report";
import { toFile } from "@/notebook/storage";
import { useNotebook } from "@/notebook/use-notebook";

const SAVE_FAILED = {
  quota:
    "Not saved: storage on this device is full. Export the notebook as JSON to keep this change.",
  unavailable:
    "Not saved: this browser does not allow storage here. Export the notebook as JSON to keep this change.",
  corrupt: "Not saved: the stored data cannot be read. Download or reset it first.",
} as const;

export function NotebookApp({
  companies,
  initialScenario,
}: {
  companies: CompanyNames;
  initialScenario: string | null;
}) {
  const { notebook, status, unreadable, ready, save, reset } = useNotebook();
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(initialScenario);
  const [message, setMessage] = useState<{ text: string; tone: "ok" | "warn" } | null>(null);
  const [importErrors, setImportErrors] = useState<string[]>([]);

  const results = useMemo(
    () => searchScenarios(notebook, query, tag, companies),
    [notebook, query, tag, companies],
  );
  const record = selected ? findScenario(notebook, selected) : undefined;

  const select = (scenarioId: string | null) => {
    setSelected(scenarioId);
    const url = scenarioId ? `/notebook?scenario=${scenarioId}` : "/notebook";
    window.history.replaceState(null, "", url);
  };

  const commit = (next: Notebook, done: string) => {
    const result = save(next);
    setMessage(
      result.ok ? { text: done, tone: "ok" } : { text: SAVE_FAILED[result.status], tone: "warn" },
    );
  };

  const importFile = async (file: File) => {
    setImportErrors([]);
    const parsed = await parseNotebookFile(await file.text());
    if (!parsed.ok) {
      setImportErrors(parsed.errors.slice(0, 12));
      setMessage({ text: `Nothing was imported from ${file.name}.`, tone: "warn" });
      return;
    }
    const merged = mergeNotebook(notebook, parsed.file.notebook);
    const parts = [
      `${merged.added} added`,
      merged.copied > 0
        ? `${merged.copied} imported as copies because the same ID already exists here`
        : null,
      merged.unchanged > 0 ? `${merged.unchanged} already here` : null,
      `${merged.reportsAdded} reports added`,
      merged.reportsSkipped > 0
        ? `${merged.reportsSkipped} reports of copied scenarios left out`
        : null,
      ...parsed.file.migrations,
    ].filter(Boolean);
    commit(merged.notebook, `Imported ${file.name}: ${parts.join("; ")}.`);
  };

  const exportReport = async (scenarioId: string, revisionNumber: number) => {
    const target = findScenario(notebook, scenarioId);
    const revision = target?.revisions[revisionNumber - 1];
    if (!target || !revision) return;
    const report = await buildReport(target, revision, companies, SYSTEM_CLOCK);
    downloadText(report.file_name, report.content, "text/markdown;charset=utf-8");
    commit(
      addReport(notebook, report),
      `Exported a report of revision ${revisionNumber}. It is kept as it is; the revision is now locked.`,
    );
  };

  if (!ready) {
    return <p className="text-body text-ink-muted">Reading the notebook on this device…</p>;
  }

  return (
    <div className="flex flex-col gap-8">
      <StorageBanner
        status={status}
        unreadable={unreadable}
        onReset={() => {
          reset();
          setMessage({
            text: "The unreadable data was deleted. The notebook is empty.",
            tone: "ok",
          });
        }}
      />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="flex min-w-0 flex-col gap-1.5 lg:flex-1">
          <label htmlFor="notebook-search" className="text-small font-medium text-ink">
            Search
          </label>
          <input
            id="notebook-search"
            type="search"
            placeholder="Name, tag, notes or company"
            value={query}
            onChange={(event) => setQuery(event.target.value.slice(0, 64))}
            className={CONTROL}
          />
        </div>
        <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="sm:w-48">
            <SelectField
              id="notebook-tag"
              label="Tag"
              value={tag ?? ""}
              onChange={(event) => setTag(event.target.value || null)}
            >
              <option value="">All tags</option>
              {allTags(notebook).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </SelectField>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                const stamp = new Date().toISOString();
                downloadText(
                  `multiverse_notebook_${stamp.slice(0, 10)}_DEMO.json`,
                  `${JSON.stringify(toFile(notebook, stamp), null, 2)}\n`,
                  "application/json",
                );
              }}
            >
              <Download aria-hidden="true" />
              Export notebook
            </Button>
            <label
              className={cn(
                buttonClasses({ variant: "secondary" }),
                "cursor-pointer has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-mint",
              )}
            >
              <Upload aria-hidden="true" />
              Import JSON
              <input
                type="file"
                accept="application/json,.json"
                className="sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file) void importFile(file);
                }}
              />
            </label>
          </div>
        </div>
      </div>

      <div role="status" className="empty:hidden">
        {message ? (
          <p className={cn("text-small", message.tone === "ok" ? "text-mint" : "text-warning")}>
            {message.text}
          </p>
        ) : null}
      </div>
      {importErrors.length > 0 ? (
        <div className="rounded-panel border border-negative/50 bg-surface p-4" role="alert">
          <p className="font-medium text-ink">The file was rejected</p>
          <ul className="mt-2 list-disc pl-5 text-small text-ink-muted">
            {importErrors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {notebook.scenarios.length === 0 ? (
        <div className="flex max-w-prose flex-col gap-3 rounded-panel border border-line bg-surface p-6">
          <p className="font-medium text-ink">No saved scenarios yet</p>
          <p className="text-small text-ink-muted">
            Build and validate a decision, then choose Save to notebook. You can also import a
            notebook or a decision file exported earlier.
          </p>
          <div>
            <Link href="/decisions" className={buttonClasses({ variant: "secondary", size: "sm" })}>
              Open the Decision Builder
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <section aria-labelledby="list-title" className="flex min-w-0 flex-col gap-3">
            <h2 id="list-title" className="text-small font-medium text-ink">
              {results.length} of {notebook.scenarios.length}{" "}
              {notebook.scenarios.length === 1 ? "scenario" : "scenarios"}
            </h2>
            <ul className="flex flex-col gap-2">
              {results.map((item) => {
                const latest = latestRevision(item);
                const company = companies[latest.draft.company_id];
                const active = item.scenario_id === selected;
                return (
                  <li key={item.scenario_id}>
                    <button
                      type="button"
                      aria-current={active ? "true" : undefined}
                      onClick={() => select(item.scenario_id)}
                      className={cn(
                        "flex w-full flex-col gap-1 rounded-panel border p-3 text-left",
                        active
                          ? "border-mint bg-inset"
                          : "border-line bg-surface hover:border-line-strong",
                      )}
                    >
                      <span className="font-medium text-ink">{item.name}</span>
                      <span className="text-small text-ink-muted">
                        {company?.name ?? "Unknown company"} · {item.revisions.length}{" "}
                        {item.revisions.length === 1 ? "revision" : "revisions"}
                      </span>
                      <span className="text-micro text-ink-muted">{decisionSummary(latest)}</span>
                      <span className="flex flex-wrap gap-1.5">
                        {item.tags.map((itemTag) => (
                          <Badge key={itemTag}>{itemTag}</Badge>
                        ))}
                        {item.revisions.some((revision) => revision.exported) ? (
                          <Badge tone="blue" icon={Lock}>
                            Exported
                          </Badge>
                        ) : null}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            {results.length === 0 ? (
              <p className="text-small text-ink-muted">No scenario matches.</p>
            ) : null}
          </section>

          {record ? (
            <ScenarioDetail
              key={`${record.scenario_id}-${record.updated_at}`}
              record={record}
              notebook={notebook}
              companies={companies}
              onSaveMeta={(meta) =>
                commit(
                  updateMeta(notebook, record.scenario_id, meta),
                  "Details saved. The revisions did not change.",
                )
              }
              onDuplicate={(revision) => {
                const { notebook: next, ref } = duplicateRevision(notebook, {
                  scenario_id: record.scenario_id,
                  revision,
                });
                commit(next, `Duplicated revision ${revision} as a new scenario.`);
                select(ref.scenario_id);
              }}
              onExport={(revision) => void exportReport(record.scenario_id, revision)}
              onDelete={() => {
                commit(deleteScenario(notebook, record.scenario_id), `Deleted “${record.name}”.`);
                select(null);
              }}
            />
          ) : (
            <p className="text-body text-ink-muted">
              Choose a scenario to see its revisions, reports and comparisons.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
