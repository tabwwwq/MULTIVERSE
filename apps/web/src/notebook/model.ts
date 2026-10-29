import type {
  ReportSnapshot,
  RevisionRef,
  ScenarioDraft,
  ScenarioRecord,
  ScenarioRevision,
} from "@multiverse/contracts";

/*
 * The research notebook (PRD FR-LB): scenarios with editable metadata and append-only
 * revisions, plus report snapshots that are never edited or replaced. Every function
 * here is pure: it returns a new notebook and leaves the old one untouched, so the
 * storage layer can write, retry or roll back as a whole.
 */

export interface Notebook {
  scenarios: ScenarioRecord[];
  reports: ReportSnapshot[];
}

export const EMPTY_NOTEBOOK: Notebook = { scenarios: [], reports: [] };

export interface Clock {
  now: () => string;
  id: () => string;
}

export const SYSTEM_CLOCK: Clock = {
  now: () => new Date().toISOString(),
  id: () => crypto.randomUUID(),
};

export interface ScenarioMeta {
  name: string;
  tags: string[];
  notes: string;
}

export const TAG_PATTERN = /^[a-z0-9][a-z0-9-]{0,31}$/;

type Revisions = ScenarioRecord["revisions"];

/** Revisions are never empty; the contract type says so. */
function revisionList(items: ScenarioRevision[]): Revisions {
  const [first, ...rest] = items;
  if (!first) throw new Error("A scenario has at least one revision.");
  return [first, ...rest];
}
export const MAX_TAGS = 10;

/** "R&D, Northwind 2022" -> ["rnd", "northwind-2022"]; invalid pieces are dropped. */
export function parseTags(text: string): string[] {
  const tags = text
    .split(",")
    .map((tag) =>
      tag
        .trim()
        .toLowerCase()
        .replaceAll("&", "n")
        .replace(/[^a-z0-9-]+/g, "-")
        .replace(/^-+|-+$/g, ""),
    )
    .filter((tag) => TAG_PATTERN.test(tag));
  return [...new Set(tags)].slice(0, MAX_TAGS);
}

export function metaIssues(meta: ScenarioMeta): string[] {
  const issues: string[] = [];
  const name = meta.name.trim();
  if (name === "") issues.push("Enter a name.");
  if (name.length > 120) issues.push("Keep the name under 120 characters.");
  if (meta.notes.length > 5000) issues.push("Keep the notes under 5,000 characters.");
  return issues;
}

function newRevision(
  number: number,
  draft: ScenarioDraft,
  clock: Clock,
  parent: number | null,
  derivedFrom: RevisionRef | null,
): ScenarioRevision {
  return {
    revision: number,
    parent_revision: parent,
    derived_from: derivedFrom,
    created_at: clock.now(),
    draft,
    mode: "demo",
    currency: "USD",
    result_status: "not_run",
    result_id: null,
    exported: false,
  };
}

export function findScenario(notebook: Notebook, scenarioId: string): ScenarioRecord | undefined {
  return notebook.scenarios.find((record) => record.scenario_id === scenarioId);
}

export function findRevision(notebook: Notebook, ref: RevisionRef): ScenarioRevision | undefined {
  return findScenario(notebook, ref.scenario_id)?.revisions[ref.revision - 1];
}

export function latestRevision(record: ScenarioRecord): ScenarioRevision {
  return record.revisions[record.revisions.length - 1] as ScenarioRevision;
}

/** A new scenario with its first revision. */
export function createScenario(
  notebook: Notebook,
  draft: ScenarioDraft,
  meta: ScenarioMeta,
  clock: Clock = SYSTEM_CLOCK,
): { notebook: Notebook; ref: RevisionRef } {
  const now = clock.now();
  const record: ScenarioRecord = {
    scenario_id: clock.id(),
    name: meta.name.trim(),
    tags: meta.tags,
    notes: meta.notes,
    created_at: now,
    updated_at: now,
    revisions: revisionList([newRevision(1, draft, clock, null, null)]),
  };
  return {
    notebook: { ...notebook, scenarios: [record, ...notebook.scenarios] },
    ref: { scenario_id: record.scenario_id, revision: 1 },
  };
}

/** A new revision that names the revision it was edited from. Earlier ones stay as they are. */
export function addRevision(
  notebook: Notebook,
  scenarioId: string,
  draft: ScenarioDraft,
  parent: number,
  clock: Clock = SYSTEM_CLOCK,
): { notebook: Notebook; ref: RevisionRef } {
  const record = findScenario(notebook, scenarioId);
  if (!record) throw new Error(`No scenario ${scenarioId}`);
  if (draft.company_id !== record.revisions[0]?.draft.company_id) {
    throw new Error(
      "A revision keeps the scenario's company; save another company as a new scenario.",
    );
  }
  const number = record.revisions.length + 1;
  const updated: ScenarioRecord = {
    ...record,
    updated_at: clock.now(),
    revisions: revisionList([...record.revisions, newRevision(number, draft, clock, parent, null)]),
  };
  return {
    notebook: replaceScenario(notebook, updated),
    ref: { scenario_id: scenarioId, revision: number },
  };
}

/** Duplicate a revision into a new scenario that records where it came from. */
export function duplicateRevision(
  notebook: Notebook,
  ref: RevisionRef,
  clock: Clock = SYSTEM_CLOCK,
): { notebook: Notebook; ref: RevisionRef } {
  const record = findScenario(notebook, ref.scenario_id);
  const source = findRevision(notebook, ref);
  if (!record || !source) throw new Error("No such revision");
  const now = clock.now();
  const copy: ScenarioRecord = {
    scenario_id: clock.id(),
    name: `${record.name} (copy of r${ref.revision})`.slice(0, 120),
    tags: record.tags,
    notes: record.notes,
    created_at: now,
    updated_at: now,
    revisions: revisionList([newRevision(1, source.draft, clock, null, ref)]),
  };
  return {
    notebook: { ...notebook, scenarios: [copy, ...notebook.scenarios] },
    ref: { scenario_id: copy.scenario_id, revision: 1 },
  };
}

function replaceScenario(notebook: Notebook, record: ScenarioRecord): Notebook {
  return {
    ...notebook,
    scenarios: notebook.scenarios.map((item) =>
      item.scenario_id === record.scenario_id ? record : item,
    ),
  };
}

/** Name, tags and notes describe the scenario; they never change a revision. */
export function updateMeta(
  notebook: Notebook,
  scenarioId: string,
  meta: ScenarioMeta,
  clock: Clock = SYSTEM_CLOCK,
): Notebook {
  const record = findScenario(notebook, scenarioId);
  if (!record) throw new Error(`No scenario ${scenarioId}`);
  return replaceScenario(notebook, {
    ...record,
    name: meta.name.trim(),
    tags: meta.tags,
    notes: meta.notes,
    updated_at: clock.now(),
  });
}

/** A scenario that has exported reports cannot be deleted: the reports point at it. */
export function deleteScenario(notebook: Notebook, scenarioId: string): Notebook {
  if (notebook.reports.some((report) => report.source.scenario_id === scenarioId)) {
    throw new Error("This scenario has exported reports and cannot be deleted.");
  }
  return { ...notebook, scenarios: notebook.scenarios.filter((r) => r.scenario_id !== scenarioId) };
}

/** Appends a report and locks its revision. Existing reports are never touched. */
export function addReport(notebook: Notebook, report: ReportSnapshot): Notebook {
  const record = findScenario(notebook, report.source.scenario_id);
  if (!record) throw new Error("No such scenario");
  const locked: ScenarioRecord = {
    ...record,
    revisions: revisionList(
      record.revisions.map((revision) =>
        revision.revision === report.source.revision ? { ...revision, exported: true } : revision,
      ),
    ),
  };
  return {
    scenarios: replaceScenario(notebook, locked).scenarios,
    reports: [...notebook.reports, report],
  };
}

export function reportsFor(notebook: Notebook, ref: RevisionRef): ReportSnapshot[] {
  return notebook.reports.filter(
    (report) =>
      report.source.scenario_id === ref.scenario_id && report.source.revision === ref.revision,
  );
}

export interface CompanyNames {
  [companyId: string]: { name: string; ticker: string | null } | undefined;
}

/** Search by name, tag, notes or company; an optional tag must match exactly. */
export function searchScenarios(
  notebook: Notebook,
  query: string,
  tag: string | null,
  companies: CompanyNames,
): ScenarioRecord[] {
  const needle = query.trim().toLowerCase();
  return notebook.scenarios
    .filter((record) => tag === null || record.tags.includes(tag))
    .filter((record) => {
      if (needle === "") return true;
      const company = companies[record.revisions[0]?.draft.company_id ?? ""];
      const haystack = [
        record.name,
        record.notes,
        ...record.tags,
        company?.name ?? "",
        company?.ticker ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    })
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function allTags(notebook: Notebook): string[] {
  return [...new Set(notebook.scenarios.flatMap((record) => record.tags))].sort();
}
