import type {
  ReportSnapshot,
  ScenarioDraft,
  ScenarioRecord,
  ScenarioRevision,
} from "@multiverse/contracts";
import { CONTRACTS_VERSION } from "@multiverse/contracts";
import { parseScenarioDraft } from "@/decisions/parse";
import {
  type Clock,
  findScenario,
  type Notebook,
  SYSTEM_CLOCK,
  TAG_PATTERN,
} from "@/notebook/model";
import { sha256Hex } from "@/notebook/report";
import { SCHEMA_VERSION } from "@/notebook/storage";

/*
 * Reading a notebook file (PRD FR-LB-03). The checks mirror the Python NotebookExport
 * contract: structure, revision numbering, result status, report hashes and links.
 * Older formats are migrated, files from a newer version are refused, and nothing is
 * merged unless the whole file is valid. Merging never overwrites: a scenario whose ID
 * already exists with different content comes in as a copy.
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const HEX64 = /^[0-9a-f]{64}$/;

type Json = Record<string, unknown>;

export interface ParsedFile {
  notebook: Notebook;
  /** What was migrated, in plain words. */
  migrations: string[];
}

export type ParseResult = { ok: true; file: ParsedFile } | { ok: false; errors: string[] };

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** -1, 0 or 1 for two "x.y.z" versions. */
export function compareVersions(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < 3; i += 1) {
    const diff = (left[i] ?? 0) - (right[i] ?? 0);
    if (diff !== 0) return Math.sign(diff);
  }
  return 0;
}

class Checker {
  readonly errors: string[] = [];

  keys(value: Json, where: string, allowed: readonly string[]): void {
    for (const key of Object.keys(value)) {
      if (!allowed.includes(key)) this.errors.push(`${where}: unknown field "${key}".`);
    }
    for (const key of allowed) {
      if (!(key in value)) this.errors.push(`${where}: missing field "${key}".`);
    }
  }

  check(condition: boolean, message: string): void {
    if (!condition) this.errors.push(message);
  }
}

const REVISION_KEYS = [
  "revision",
  "parent_revision",
  "derived_from",
  "created_at",
  "draft",
  "mode",
  "currency",
  "result_status",
  "result_id",
  "exported",
] as const;
const SCENARIO_KEYS = [
  "scenario_id",
  "name",
  "tags",
  "notes",
  "created_at",
  "updated_at",
  "revisions",
] as const;
const REPORT_KEYS = [
  "report_id",
  "source",
  "created_at",
  "format",
  "file_name",
  "content",
  "content_sha256",
  "manifest",
] as const;

function checkDraft(checker: Checker, value: unknown, where: string): ScenarioDraft | null {
  if (isObject(value) && typeof value["contracts_version"] === "string") {
    if (compareVersions(value["contracts_version"], CONTRACTS_VERSION) > 0) {
      checker.errors.push(
        `${where}: written by a newer version (contracts ${value["contracts_version"]}).`,
      );
      return null;
    }
  }
  const parsed = parseScenarioDraft(value);
  for (const issue of parsed.issues)
    checker.errors.push(`${where}: ${issue.path} ${issue.message}`);
  return parsed.draft;
}

function checkRevision(
  checker: Checker,
  value: unknown,
  index: number,
  where: string,
): ScenarioRevision | null {
  const here = `${where}, revision ${index + 1}`;
  if (!isObject(value)) {
    checker.errors.push(`${here}: not an object.`);
    return null;
  }
  checker.keys(value, here, REVISION_KEYS);
  const number = value["revision"];
  const parent = value["parent_revision"];
  checker.check(number === index + 1, `${here}: revisions must be numbered 1, 2, 3 without gaps.`);
  checker.check(
    parent === null ||
      (typeof parent === "number" && Number.isInteger(parent) && parent >= 1 && parent < index + 1),
    `${here}: the parent must be an earlier revision.`,
  );
  if (index === 0) checker.check(parent === null, `${here}: the first revision has no parent.`);
  checker.check(
    typeof value["created_at"] === "string" && DATETIME.test(value["created_at"]),
    `${here}: created_at must be a date and time with a time zone.`,
  );
  checker.check(value["mode"] === "demo", `${here}: only demo scenarios exist in this version.`);
  checker.check(value["currency"] === "USD", `${here}: the currency is USD (decision D-04).`);
  const status = value["result_status"];
  const resultId = value["result_id"];
  checker.check(
    ["not_run", "completed", "failed"].includes(String(status)),
    `${here}: unknown result status.`,
  );
  checker.check(
    (status === "not_run") === (resultId === null) &&
      (resultId === null || (typeof resultId === "string" && UUID.test(resultId))),
    `${here}: a result ID belongs to, and only to, a run result.`,
  );
  checker.check(typeof value["exported"] === "boolean", `${here}: exported must be true or false.`);
  const derived = value["derived_from"];
  checker.check(
    derived === null ||
      (isObject(derived) &&
        typeof derived["scenario_id"] === "string" &&
        UUID.test(derived["scenario_id"]) &&
        typeof derived["revision"] === "number"),
    `${here}: derived_from must name a scenario and a revision.`,
  );
  const draft = checkDraft(checker, value["draft"], here);
  return draft ? ({ ...(value as unknown as ScenarioRevision), draft } as ScenarioRevision) : null;
}

function checkScenario(checker: Checker, value: unknown, index: number): ScenarioRecord | null {
  const where = `Scenario ${index + 1}`;
  if (!isObject(value)) {
    checker.errors.push(`${where}: not an object.`);
    return null;
  }
  checker.keys(value, where, SCENARIO_KEYS);
  const id = value["scenario_id"];
  const name = value["name"];
  const tags = value["tags"];
  checker.check(typeof id === "string" && UUID.test(id), `${where}: scenario_id must be a UUID.`);
  checker.check(
    typeof name === "string" && name.trim() === name && name.length >= 1 && name.length <= 120,
    `${where}: the name is 1 to 120 characters without surrounding spaces.`,
  );
  checker.check(
    Array.isArray(tags) &&
      tags.length <= 10 &&
      new Set(tags).size === tags.length &&
      tags.every((tag) => typeof tag === "string" && TAG_PATTERN.test(tag)),
    `${where}: up to 10 unique tags of lowercase letters, digits and dashes.`,
  );
  checker.check(
    typeof value["notes"] === "string" && value["notes"].length <= 5000,
    `${where}: notes are text up to 5,000 characters.`,
  );
  const created = value["created_at"];
  const updated = value["updated_at"];
  checker.check(
    typeof created === "string" && DATETIME.test(created),
    `${where}: created_at must be a date and time with a time zone.`,
  );
  checker.check(
    typeof updated === "string" &&
      DATETIME.test(updated) &&
      typeof created === "string" &&
      Date.parse(updated) >= Date.parse(created),
    `${where}: updated_at cannot come before created_at.`,
  );
  const revisions = value["revisions"];
  if (!Array.isArray(revisions) || revisions.length === 0) {
    checker.errors.push(`${where}: at least one revision.`);
    return null;
  }
  const parsed = revisions.map((revision, i) => checkRevision(checker, revision, i, where));
  const company = parsed[0]?.draft.company_id;
  checker.check(
    parsed.every((revision) => revision === null || revision.draft.company_id === company),
    `${where}: all revisions are for the same company.`,
  );
  return {
    ...(value as unknown as ScenarioRecord),
    revisions: parsed as ScenarioRecord["revisions"],
  };
}

async function checkReport(
  checker: Checker,
  value: unknown,
  index: number,
  scenarios: readonly ScenarioRecord[],
): Promise<ReportSnapshot | null> {
  const where = `Report ${index + 1}`;
  if (!isObject(value)) {
    checker.errors.push(`${where}: not an object.`);
    return null;
  }
  checker.keys(value, where, REPORT_KEYS);
  const source = value["source"];
  const content = value["content"];
  const hash = value["content_sha256"];
  const manifest = value["manifest"];
  checker.check(
    typeof value["report_id"] === "string" && UUID.test(value["report_id"]),
    `${where}: report_id must be a UUID.`,
  );
  checker.check(value["format"] === "markdown", `${where}: only Markdown reports exist.`);
  if (
    !isObject(source) ||
    typeof source["scenario_id"] !== "string" ||
    typeof source["revision"] !== "number"
  ) {
    checker.errors.push(`${where}: source must name a scenario and a revision.`);
    return null;
  }
  const record = scenarios.find((item) => item.scenario_id === source["scenario_id"]);
  // A revision that failed its own checks is null here; its errors are already listed.
  const revision = record?.revisions[source["revision"] - 1] as ScenarioRevision | null | undefined;
  checker.check(
    revision !== undefined && revision !== null,
    `${where}: names a revision that is not in the file.`,
  );
  checker.check(
    revision === undefined || revision === null || revision.exported,
    `${where}: its revision is not marked exported.`,
  );
  if (typeof content !== "string" || typeof hash !== "string" || !HEX64.test(hash)) {
    checker.errors.push(`${where}: content and a SHA-256 hash are required.`);
    return null;
  }
  checker.check(
    (await sha256Hex(content)) === hash,
    `${where}: the content does not match its SHA-256 hash; it was changed after export.`,
  );
  checker.check(
    isObject(manifest) &&
      manifest["scenario_id"] === source["scenario_id"] &&
      manifest["revision"] === source["revision"],
    `${where}: the manifest must name the exported scenario and revision.`,
  );
  const fileName = value["file_name"];
  checker.check(
    typeof fileName === "string" &&
      /^[A-Za-z0-9_.-]+\.md$/.test(fileName) &&
      (!isObject(manifest) ||
        manifest["data_origin"] !== "synthetic" ||
        fileName.endsWith("_DEMO.md")),
    `${where}: a demo report file name ends with _DEMO.md.`,
  );
  return value as unknown as ReportSnapshot;
}

function wrapDraft(draft: ScenarioDraft, clock: Clock): ScenarioRecord {
  const now = clock.now();
  return {
    scenario_id: clock.id(),
    name: `Imported ${draft.decision.type.replaceAll("_", " ")} at ${draft.as_of}`,
    tags: ["imported"],
    notes: "",
    created_at: now,
    updated_at: now,
    revisions: [
      {
        revision: 1,
        parent_revision: null,
        derived_from: null,
        created_at: now,
        draft,
        mode: "demo",
        currency: "USD",
        result_status: "not_run",
        result_id: null,
        exported: false,
      },
    ],
  };
}

/** Parses an exported notebook, or a decision file from the Decision Builder (migrated). */
export async function parseNotebookFile(
  text: string,
  clock: Clock = SYSTEM_CLOCK,
): Promise<ParseResult> {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { ok: false, errors: ["The file is not valid JSON."] };
  }
  if (!isObject(value))
    return { ok: false, errors: ["The file holds no MULTIVERSE notebook or decision."] };

  if (value["format"] !== "multiverse-notebook") {
    if ("decision" in value && "company_id" in value) {
      const checker = new Checker();
      const draft = checkDraft(checker, value, "Decision file");
      if (!draft) return { ok: false, errors: checker.errors };
      return {
        ok: true,
        file: {
          notebook: { scenarios: [wrapDraft(draft, clock)], reports: [] },
          migrations: [
            `A decision file (contracts ${draft.contracts_version}) became a new scenario with one revision.`,
          ],
        },
      };
    }
    return { ok: false, errors: ["The file holds no MULTIVERSE notebook or decision."] };
  }

  const checker = new Checker();
  checker.keys(value, "File", [
    "format",
    "schema_version",
    "contracts_version",
    "exported_at",
    "scenarios",
    "reports",
  ]);
  const schema = value["schema_version"];
  if (typeof schema !== "number" || !Number.isInteger(schema) || schema < 1) {
    return { ok: false, errors: ["File: schema_version must be a whole number from 1."] };
  }
  if (schema > SCHEMA_VERSION) {
    return {
      ok: false,
      errors: [
        `File: written by a newer version of MULTIVERSE (notebook schema ${schema}). Update the app to read it.`,
      ],
    };
  }
  const scenariosRaw = value["scenarios"];
  const reportsRaw = value["reports"];
  if (!Array.isArray(scenariosRaw) || !Array.isArray(reportsRaw)) {
    return { ok: false, errors: [...checker.errors, "File: scenarios and reports must be lists."] };
  }
  const scenarios = scenariosRaw
    .map((item, i) => checkScenario(checker, item, i))
    .filter((item): item is ScenarioRecord => item !== null);
  const ids = scenarios.map((record) => record.scenario_id);
  checker.check(new Set(ids).size === ids.length, "File: scenario IDs must be unique.");
  const reports: ReportSnapshot[] = [];
  for (const [i, item] of reportsRaw.entries()) {
    const report = await checkReport(checker, item, i, scenarios);
    if (report) reports.push(report);
  }
  checker.check(
    new Set(reports.map((report) => report.report_id)).size === reports.length,
    "File: report IDs must be unique.",
  );
  if (checker.errors.length > 0) return { ok: false, errors: checker.errors };
  return { ok: true, file: { notebook: { scenarios, reports }, migrations: [] } };
}

export interface MergeSummary {
  notebook: Notebook;
  added: number;
  copied: number;
  unchanged: number;
  reportsAdded: number;
  /** Reports of scenarios that came in as copies: their manifests name the original ID. */
  reportsSkipped: number;
}

/** Adds imported scenarios and reports. Existing ones are never replaced. */
export function mergeNotebook(
  target: Notebook,
  incoming: Notebook,
  clock: Clock = SYSTEM_CLOCK,
): MergeSummary {
  let scenarios = [...target.scenarios];
  let reports = [...target.reports];
  const idMap = new Map<string, string>();
  let added = 0;
  let copied = 0;
  let unchanged = 0;
  for (const record of incoming.scenarios) {
    const existing = findScenario({ scenarios, reports }, record.scenario_id);
    if (!existing) {
      scenarios = [record, ...scenarios];
      added += 1;
    } else if (JSON.stringify(existing) === JSON.stringify(record)) {
      unchanged += 1;
    } else {
      const copyId = clock.id();
      idMap.set(record.scenario_id, copyId);
      scenarios = [
        { ...record, scenario_id: copyId, name: `${record.name} (imported copy)`.slice(0, 120) },
        ...scenarios,
      ];
      copied += 1;
    }
  }
  let reportsAdded = 0;
  let reportsSkipped = 0;
  for (const report of incoming.reports) {
    if (reports.some((item) => item.report_id === report.report_id)) continue;
    // A report is immutable and its manifest names the original scenario, so it cannot
    // be re-pointed at a copy.
    if (idMap.has(report.source.scenario_id)) {
      reportsSkipped += 1;
      continue;
    }
    reports = [...reports, report];
    reportsAdded += 1;
  }
  // A copied scenario has no report, so its revisions are not locked by one.
  scenarios = scenarios.map((record) =>
    [...idMap.values()].includes(record.scenario_id)
      ? {
          ...record,
          revisions: record.revisions.map((revision) => ({
            ...revision,
            exported: false,
          })) as ScenarioRecord["revisions"],
        }
      : record,
  );
  return {
    notebook: { scenarios, reports },
    added,
    copied,
    unchanged,
    reportsAdded,
    reportsSkipped,
  };
}
