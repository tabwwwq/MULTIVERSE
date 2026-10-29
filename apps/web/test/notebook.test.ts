import { readFileSync } from "node:fs";
import type { ScenarioDraft } from "@multiverse/contracts";
import { describe, expect, it } from "vitest";
import { compareRevisions } from "@/notebook/compare";
import { mergeNotebook, parseNotebookFile } from "@/notebook/import";
import {
  addReport,
  addRevision,
  type Clock,
  createScenario,
  deleteScenario,
  duplicateRevision,
  EMPTY_NOTEBOOK,
  findRevision,
  type Notebook,
  parseTags,
  searchScenarios,
  updateMeta,
} from "@/notebook/model";
import { buildReport, sha256Hex } from "@/notebook/report";
import {
  deleteAll,
  inventory,
  loadNotebook,
  NOTEBOOK_KEY,
  type StorageLike,
  toFile,
  writeNotebook,
} from "@/notebook/storage";

const FIXTURES = new URL("../../../packages/contracts/fixtures/", import.meta.url);
const EXPORT_TEXT = readFileSync(new URL("notebook/valid-export.json", FIXTURES), "utf8");
const DRAFTS = (
  JSON.parse(readFileSync(new URL("valid.json", FIXTURES), "utf8")) as {
    model: string;
    payload: ScenarioDraft;
  }[]
)
  .filter((item) => item.model === "ScenarioDraft")
  .map((item) => item.payload);
const RND = DRAFTS[0] as ScenarioDraft;
const RND_PP = DRAFTS[1] as ScenarioDraft;
const OTHER_CUTOFF: ScenarioDraft = { ...RND, as_of: "2022-09-30" };
const COMPANIES = { [RND.company_id]: { name: "Northwind Semiconductors Inc.", ticker: "NWSC" } };

function testClock(): Clock {
  let tick = 0;
  return {
    now: () => `2026-10-28T10:${String(tick++).padStart(2, "0")}:00.000Z`,
    id: () => `00000000-0000-4000-8000-${String(tick++).padStart(12, "0")}`,
  };
}

class FakeStorage implements StorageLike {
  readonly items = new Map<string, string>();
  failWith: Error | null = null;
  get length() {
    return this.items.size;
  }
  key(index: number) {
    return [...this.items.keys()][index] ?? null;
  }
  getItem(key: string) {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    if (this.failWith) throw this.failWith;
    this.items.set(key, value);
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
}

function seeded(): { notebook: Notebook; scenarioId: string; clock: Clock } {
  const clock = testClock();
  const created = createScenario(
    EMPTY_NOTEBOOK,
    RND,
    { name: "Northwind R&D", tags: ["rnd"], notes: "First" },
    clock,
  );
  return { notebook: created.notebook, scenarioId: created.ref.scenario_id, clock };
}

describe("scenarios and revisions", () => {
  it("saves a scenario with name, tags, notes and a first revision", () => {
    const { notebook } = seeded();
    const record = notebook.scenarios[0];
    expect(record?.name).toBe("Northwind R&D");
    expect(record?.revisions).toHaveLength(1);
    expect(record?.revisions[0]).toMatchObject({
      revision: 1,
      parent_revision: null,
      result_status: "not_run",
      mode: "demo",
      currency: "USD",
      exported: false,
    });
    expect(record?.revisions[0]?.draft).toEqual(RND);
  });

  it("adds a revision that names its parent and leaves earlier revisions untouched", () => {
    const { notebook, scenarioId, clock } = seeded();
    const before = JSON.stringify(notebook.scenarios[0]?.revisions[0]);
    const { notebook: next, ref } = addRevision(notebook, scenarioId, RND_PP, 1, clock);
    expect(ref.revision).toBe(2);
    expect(findRevision(next, ref)?.parent_revision).toBe(1);
    expect(JSON.stringify(next.scenarios[0]?.revisions[0])).toBe(before);
    expect(notebook.scenarios[0]?.revisions).toHaveLength(1);
  });

  it("refuses a revision for another company", () => {
    const { notebook, scenarioId, clock } = seeded();
    const other = { ...RND, company_id: "a7c2e9d4-1f3b-4c8a-b5e6-0d9f2a7c3e18" };
    expect(() => addRevision(notebook, scenarioId, other, 1, clock)).toThrow(/company/);
  });

  it("duplicates a revision into a new scenario that records its source", () => {
    const { notebook, scenarioId, clock } = seeded();
    const { notebook: next, ref } = duplicateRevision(
      notebook,
      { scenario_id: scenarioId, revision: 1 },
      clock,
    );
    expect(next.scenarios).toHaveLength(2);
    expect(findRevision(next, ref)?.derived_from).toEqual({ scenario_id: scenarioId, revision: 1 });
    expect(next.scenarios.find((r) => r.scenario_id === scenarioId)).toEqual(notebook.scenarios[0]);
  });

  it("edits metadata without touching revisions", () => {
    const { notebook, scenarioId, clock } = seeded();
    const next = updateMeta(
      notebook,
      scenarioId,
      { name: "Renamed", tags: ["x"], notes: "" },
      clock,
    );
    expect(next.scenarios[0]?.name).toBe("Renamed");
    expect(next.scenarios[0]?.revisions).toEqual(notebook.scenarios[0]?.revisions);
  });

  it("finds scenarios by name, tag, notes or company", () => {
    const { notebook } = seeded();
    expect(searchScenarios(notebook, "northwind", null, COMPANIES)).toHaveLength(1);
    expect(searchScenarios(notebook, "nwsc", null, COMPANIES)).toHaveLength(1);
    expect(searchScenarios(notebook, "first", null, COMPANIES)).toHaveLength(1);
    expect(searchScenarios(notebook, "", "rnd", COMPANIES)).toHaveLength(1);
    expect(searchScenarios(notebook, "", "capex", COMPANIES)).toHaveLength(0);
  });

  it("turns typed tags into valid ones", () => {
    expect(parseTags("R&D, Northwind 2022, , rnd, ***")).toEqual(["rnd", "northwind-2022"]);
  });
});

describe("reports", () => {
  it("are immutable snapshots: re-export adds one and never replaces the first (FR-RP-03)", async () => {
    const { notebook, scenarioId, clock } = seeded();
    const record = notebook.scenarios[0];
    const revision = record?.revisions[0];
    if (!record || !revision) throw new Error("seed failed");
    const first = await buildReport(record, revision, COMPANIES, clock);
    const once = addReport(notebook, first);
    const second = await buildReport(once.scenarios[0] ?? record, revision, COMPANIES, clock);
    const twice = addReport(once, second);

    expect(twice.reports).toHaveLength(2);
    expect(twice.reports[0]).toEqual(first);
    expect(second.report_id).not.toBe(first.report_id);
    expect(second.manifest).toEqual(first.manifest);
    expect(second.content_sha256).toBe(first.content_sha256);
    expect(twice.scenarios[0]?.revisions[0]?.exported).toBe(true);
    expect(() => deleteScenario(twice, scenarioId)).toThrow(/exported reports/);
  });

  it("carry the manifest, the demo warning and a matching hash (FR-RP-02, FR-RP-04)", async () => {
    const { notebook, clock } = seeded();
    const record = notebook.scenarios[0];
    const revision = record?.revisions[0];
    if (!record || !revision) throw new Error("seed failed");
    const report = await buildReport(record, revision, COMPANIES, clock);
    expect(report.content.split("\n")[0]).toMatch(/^> SYNTHETIC DEMO DATA/);
    expect(report.file_name).toMatch(/_r1_DEMO\.md$/);
    expect(report.manifest).toMatchObject({
      scenario_id: record.scenario_id,
      revision: 1,
      seed: RND.seed,
      as_of: `${RND.as_of}T23:59:59Z`,
      mode: "demo",
    });
    expect(await sha256Hex(report.content)).toBe(report.content_sha256);
    expect(report.content).toContain("| R&D change | +40% of the previous R&D budget |");
  });
});

describe("storage on this device", () => {
  it("survives a refresh: what is written is read back unchanged", () => {
    const storage = new FakeStorage();
    const { notebook } = seeded();
    expect(writeNotebook(storage, notebook, "ok", "2026-10-28T12:00:00Z")).toEqual({ ok: true });
    expect(loadNotebook(storage)).toEqual({ notebook, status: "ok", unreadable: null });
  });

  it("reports a full storage instead of losing the change silently (FC-10)", () => {
    const storage = new FakeStorage();
    storage.failWith = Object.assign(new Error("Storage quota exceeded"), {
      name: "QuotaExceededError",
    });
    expect(writeNotebook(storage, seeded().notebook, "ok", "2026-10-28T12:00:00Z")).toEqual({
      ok: false,
      status: "quota",
    });
  });

  it("works without storage in private mode and says so", () => {
    expect(loadNotebook(null).status).toBe("unavailable");
    expect(writeNotebook(null, seeded().notebook, "unavailable", "x")).toEqual({
      ok: false,
      status: "unavailable",
    });
  });

  it("keeps unreadable data and refuses to overwrite it", () => {
    const storage = new FakeStorage();
    storage.items.set(NOTEBOOK_KEY, "{not json");
    const loaded = loadNotebook(storage);
    expect(loaded.status).toBe("corrupt");
    expect(loaded.unreadable).toBe("{not json");
    expect(writeNotebook(storage, seeded().notebook, loaded.status, "x")).toEqual({
      ok: false,
      status: "corrupt",
    });
    expect(storage.items.get(NOTEBOOK_KEY)).toBe("{not json");
  });

  it("lists and deletes only this app's data (FR-ST-02)", () => {
    const storage = new FakeStorage();
    storage.items.set(NOTEBOOK_KEY, "{}");
    storage.items.set("multiverse.sidebar.collapsed", "true");
    storage.items.set("another-site", "keep");
    expect(inventory(storage).map((item) => item.key)).toEqual([
      "multiverse.notebook",
      "multiverse.sidebar.collapsed",
    ]);
    expect(deleteAll(storage)).toBe(true);
    expect([...storage.items.keys()]).toEqual(["another-site"]);
  });
});

describe("import and export (FR-LB-03)", () => {
  it("reads the shared notebook file", async () => {
    const result = await parseNotebookFile(EXPORT_TEXT);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.file.notebook.scenarios[0]?.revisions).toHaveLength(2);
      expect(result.file.notebook.reports).toHaveLength(1);
    }
  });

  it("round-trips an exported notebook", async () => {
    const { notebook, clock } = seeded();
    const record = notebook.scenarios[0];
    const revision = record?.revisions[0];
    if (!record || !revision) throw new Error("seed failed");
    const withReport = addReport(notebook, await buildReport(record, revision, COMPANIES, clock));
    const text = JSON.stringify(toFile(withReport, "2026-10-28T12:00:00Z"));
    const result = await parseNotebookFile(text);
    expect(result).toEqual({ ok: true, file: { notebook: withReport, migrations: [] } });
  });

  it("migrates a decision file from the Decision Builder into a scenario", async () => {
    const result = await parseNotebookFile(JSON.stringify(RND), testClock());
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.file.migrations[0]).toMatch(
        /decision file \(contracts 0\.3\.0\) became a new scenario/,
      );
      expect(result.file.notebook.scenarios[0]?.revisions[0]?.draft).toEqual(RND);
    }
  });

  type Json = Record<string, unknown>;
  // Index into parsed JSON in a test; fails loudly instead of using non-null assertions.
  const item = (value: unknown, index: number): Json => {
    const found = (value as Json[] | undefined)?.[index];
    if (!found) throw new Error(`fixture has no item ${index}`);
    return found;
  };
  const revisionOf = (file: Json, index: number): Json =>
    item(item(file["scenarios"], 0)["revisions"], index);
  const decisionOf = (file: Json): Json =>
    (revisionOf(file, 0)["draft"] as Json)["decision"] as Json;

  const broken: [string, (file: Json) => void, RegExp][] = [
    ["a newer notebook schema", (f) => (f["schema_version"] = 2), /newer version/],
    [
      "an unknown field such as a token",
      (f) => (f["api_token"] = "secret"),
      /unknown field "api_token"/,
    ],
    [
      "a report changed after export",
      (f) => (item(f["reports"], 0)["content"] = "edited"),
      /SHA-256/,
    ],
    ["a gap in revision numbers", (f) => (revisionOf(f, 1)["revision"] = 3), /numbered 1, 2, 3/],
    [
      "a report from an unlocked revision",
      (f) => (revisionOf(f, 0)["exported"] = false),
      /not marked exported/,
    ],
    [
      "a broken decision",
      (f) => ((decisionOf(f)["financing"] as Json)["debt"] = "0.3"),
      /shares_sum|exactly 100%/,
    ],
    [
      "a decision from a newer version",
      (f) => ((revisionOf(f, 0)["draft"] as Json)["contracts_version"] = "9.0.0"),
      /newer version \(contracts 9\.0\.0\)/,
    ],
  ];

  it.each(broken)("rejects %s with a reason", async (_name, change, reason) => {
    const file = JSON.parse(EXPORT_TEXT) as Json;
    change(file);
    const result = await parseNotebookFile(JSON.stringify(file));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.join(" ")).toMatch(reason);
  });

  it("rejects malformed JSON and foreign files", async () => {
    expect(await parseNotebookFile("{oops")).toEqual({
      ok: false,
      errors: ["The file is not valid JSON."],
    });
    expect((await parseNotebookFile('{"hello": 1}')).ok).toBe(false);
    expect((await parseNotebookFile("[]")).ok).toBe(false);
  });

  it("merges without overwriting: same ID with other content arrives as a copy", async () => {
    const parsed = await parseNotebookFile(EXPORT_TEXT);
    if (!parsed.ok) throw new Error("fixture invalid");
    const first = mergeNotebook(EMPTY_NOTEBOOK, parsed.file.notebook, testClock());
    expect(first).toMatchObject({ added: 1, copied: 0, reportsAdded: 1 });
    const again = mergeNotebook(first.notebook, parsed.file.notebook, testClock());
    expect(again).toMatchObject({ added: 0, unchanged: 1, reportsAdded: 0 });

    const edited = {
      ...parsed.file.notebook,
      scenarios: parsed.file.notebook.scenarios.map((r) => ({ ...r, name: "Edited elsewhere" })),
    };
    const conflict = mergeNotebook(first.notebook, edited, testClock());
    expect(conflict).toMatchObject({ added: 0, copied: 1, reportsSkipped: 0 });
    expect(conflict.notebook.scenarios).toHaveLength(2);
    expect(conflict.notebook.scenarios.find((r) => r.name === "Northwind R&D +40%")).toEqual(
      first.notebook.scenarios[0],
    );
  });
});

describe("comparing revisions", () => {
  it("lists what differs between comparable revisions", () => {
    const { notebook, scenarioId, clock } = seeded();
    const { notebook: next } = addRevision(notebook, scenarioId, RND_PP, 1, clock);
    const [a, b] = next.scenarios[0]?.revisions ?? [];
    if (!a || !b) throw new Error("revisions missing");
    const result = compareRevisions(a, b);
    expect(result.compatible).toBe(true);
    expect(result.diffs.map((diff) => diff.label)).toContain("R&D change");
    expect(result.diffs.find((diff) => diff.label === "R&D change")).toEqual({
      label: "R&D change",
      left: "+40% of the previous R&D budget",
      right: "+2 p.p. of revenue",
    });
  });

  it("blocks revisions with different cutoffs (FC-09)", () => {
    const { notebook, scenarioId, clock } = seeded();
    const { notebook: next } = addRevision(notebook, scenarioId, OTHER_CUTOFF, 1, clock);
    const [a, b] = next.scenarios[0]?.revisions ?? [];
    if (!a || !b) throw new Error("revisions missing");
    expect(compareRevisions(a, b)).toEqual({
      compatible: false,
      reasons: ["Different knowledge cutoffs (2022-12-31 and 2022-09-30)."],
      diffs: [],
      same: 0,
    });
  });
});
