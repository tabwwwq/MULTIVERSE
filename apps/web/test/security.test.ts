import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { ScenarioDraft, ValuationReport } from "@multiverse/contracts";
import { VALUATION_REPORT } from "@multiverse/contracts/valuation";
import { describe, expect, it } from "vitest";
import { csvCell, csvNote } from "@/lib/csv";
import { safeExternalUrl } from "@/lib/safe-url";
import { MAX_IMPORT_BYTES, parseNotebookFile } from "@/notebook/import";
import { createScenario, EMPTY_NOTEBOOK, type Clock } from "@/notebook/model";
import { markdownText, reportMarkdown } from "@/notebook/report";
import { dcfCsv, defaultInputs, stressCsv, valuate } from "@/valuation/dcf";
import { contentSecurityPolicy, securityHeaders } from "../security-headers";

const SOURCE_ROOT = join(__dirname, "..", "src");
const FIXTURES = new URL("../../../packages/contracts/fixtures/", import.meta.url);
const DRAFT = (
  JSON.parse(readFileSync(new URL("valid.json", FIXTURES), "utf8")) as {
    model: string;
    payload: ScenarioDraft;
  }[]
).find((item) => item.model === "ScenarioDraft")?.payload as ScenarioDraft;
const CLOCK: Clock = {
  now: () => "2026-11-06T10:00:00.000Z",
  id: () => "00000000-0000-4000-8000-000000000001",
};
const SINKS = [
  "dangerouslySetInnerHTML",
  ".innerHTML",
  ".outerHTML",
  "insertAdjacentHTML",
  "document.write",
  "new Function",
  "eval(",
  "srcDoc",
];

function files(folder: string): string[] {
  return readdirSync(folder).flatMap((name) => {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

describe("spreadsheet formulas in exported files", () => {
  it.each(["=1+1", "+1+1", "-1+1", "@SUM(A1)", "\tx", "\rx", '=HYPERLINK("http://evil.example")'])(
    "makes %j plain text",
    (value) => {
      const cell = csvCell(value).replace(/^"/, "");
      expect(cell.startsWith("'")).toBe(true);
    },
  );

  it.each(["-123.45", "+7", "0.5", "1e-5", "-2E3", 42, -0.25])("keeps the number %s", (value) => {
    expect(csvCell(value)).toBe(String(value));
  });

  it("quotes separators, quotes and line breaks", () => {
    expect(csvCell('a,b"c')).toBe('"a,b""c"');
    expect(csvCell("a\nb")).toBe('"a\nb"');
    expect(csvCell("a\rb")).toBe('"a\rb"');
  });

  it("leaves ordinary text alone", () => {
    expect(csvCell("Recession")).toBe("Recession");
  });

  it("keeps a heading on its line", () => {
    expect(csvNote("Acme\r\n=cmd|' /C calc'!A0")).toBe("Acme =cmd|' /C calc'!A0");
  });

  it("a hostile company name stays in its comment line of a DCF file", () => {
    const view = VALUATION_REPORT.views[1];
    if (!view) throw new Error("the report has no view with the decision");
    const result = valuate(view, defaultInputs(VALUATION_REPORT, view));
    if (!result.ok) throw new Error(result.message);
    const lines = dcfCsv("Acme\n=SUM(A1)", result).split("\n");
    expect(lines.filter((line) => line.startsWith("=")).length).toBe(0);
    expect(lines[1]).toContain("Acme =SUM(A1)");
  });

  it("a quarter labelled like a formula cannot run", () => {
    const view = VALUATION_REPORT.views[1];
    if (!view) throw new Error("the report has no view with the decision");
    const result = valuate(view, defaultInputs(VALUATION_REPORT, view));
    if (!result.ok) throw new Error(result.message);
    const lines = result.lines.map((line) => ({ ...line, label: "=2+5" }));
    expect(dcfCsv("Case", { ...result, lines })).toContain(",'=2+5,");
  });

  it("a stress named like a formula cannot run", () => {
    const stress = VALUATION_REPORT.stress.map((row) => ({ ...row, label: "=2+5" }));
    const file = stressCsv({ ...VALUATION_REPORT, stress } as ValuationReport);
    expect(file).toContain("'=2+5");
    expect(file).not.toMatch(/^=2\+5/m);
  });
});

describe("the exported Markdown report", () => {
  const hostile = '<img src=x onerror="alert(1)">';

  it("escapes markup and link syntax in free text", () => {
    expect(markdownText(hostile)).not.toContain("<");
    expect(markdownText("[a](javascript:b)")).not.toContain("](");
    expect(markdownText("plain R&D text, 5 > 4")).toBe("plain R&D text, 5 &gt; 4");
  });

  it("carries no raw tag or script link", () => {
    const meta = {
      name: hostile,
      notes: `${hostile}
[click](javascript:alert(1))`,
      tags: [hostile],
    };
    const { notebook } = createScenario(EMPTY_NOTEBOOK, DRAFT, meta, CLOCK);
    const record = notebook.scenarios[0];
    const revision = record?.revisions[0];
    if (!record || !revision) throw new Error("no scenario");
    const text = reportMarkdown(record, revision, {});
    expect(text).not.toContain("<img");
    expect(text).not.toContain("](javascript");
  });
});

describe("imported files", () => {
  it("refuses a file above the limit before parsing it", async () => {
    const found = await parseNotebookFile(" ".repeat(MAX_IMPORT_BYTES + 1));
    expect(found.ok).toBe(false);
    expect(!found.ok && found.errors[0]).toContain("too large");
  });

  it("a __proto__ key pollutes nothing", async () => {
    await parseNotebookFile('{"__proto__": {"polluted": true}, "format": "multiverse-notebook"}');
    expect(({} as Record<string, unknown>)["polluted"]).toBeUndefined();
  });
});

describe("links from data", () => {
  it.each([
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:x",
    "http://www.sec.gov/",
    "https://www.sec.gov.evil.example/",
    "https://evil.example/https://www.sec.gov/",
    "//www.sec.gov/",
  ])("does not make a link of %s", (url) => {
    expect(safeExternalUrl(url)).toBeNull();
  });
});

describe("the code of the app", () => {
  it("has no sink for HTML or code", () => {
    const found = files(SOURCE_ROOT).flatMap((path) => {
      const text = readFileSync(path, "utf8");
      return SINKS.filter((sink) => text.includes(sink)).map((sink) => `${path}: ${sink}`);
    });
    expect(found).toEqual([]);
  });

  it("puts no secret name into the bundle", () => {
    const found = files(SOURCE_ROOT).filter((path) =>
      /process\.env|NEXT_PUBLIC_|FRED_API_KEY|API_TOKEN/.test(readFileSync(path, "utf8")),
    );
    expect(found).toEqual([]);
  });

  it("opens external links without giving them the page", () => {
    const found = files(SOURCE_ROOT).filter((path) => {
      const text = readFileSync(path, "utf8");
      const blank = text.match(/<a\b[^>]*target="_blank"[^>]*>/g) ?? [];
      return blank.some((tag) => !/rel="[^"]*(noopener|noreferrer)/.test(tag));
    });
    expect(found).toEqual([]);
  });
});

describe("the headers of every page", () => {
  const policy = contentSecurityPolicy(false);

  it("allow scripts and connections only from here and the local API", () => {
    expect(policy).toContain("default-src 'self'");
    expect(policy).toContain("connect-src 'self' http://127.0.0.1:8000");
    expect(policy).not.toContain("*");
    expect(policy).not.toContain("unsafe-eval");
  });

  it("forbid framing, plugins and a foreign base", () => {
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("base-uri 'self'");
    expect(policy).toContain("form-action 'self'");
  });

  it("allow eval only while developing", () => {
    expect(contentSecurityPolicy(true)).toContain("unsafe-eval");
  });

  it("cover sniffing and referrers", () => {
    const names = securityHeaders(false).map((header) => header.key);
    expect(names).toEqual(
      expect.arrayContaining([
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
      ]),
    );
  });
});
