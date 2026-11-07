import { readFileSync } from "node:fs";
import type { ResearchReport, SourceRef } from "@multiverse/contracts";
import { describe, expect, it } from "vitest";
import { REPOSITORY_BLOB, downloadName, segments, sourceLink } from "@/reports/view";

const DOCUMENT = JSON.parse(
  readFileSync(
    new URL("../../../docs/case-studies/ma-stress/debt-financed/document.json", import.meta.url),
    "utf8",
  ),
) as ResearchReport;

function ref(target: string, kind: SourceRef["kind"] = "method"): SourceRef {
  return { ref_id: "S1", kind, label: "x", target, record: null };
}

describe("report view", () => {
  it("cuts a paragraph into text, claims and sources", () => {
    expect(segments("EV is 93.3 [C7] from the run (S5); see S12.")).toEqual([
      { kind: "text", text: "EV is 93.3 " },
      { kind: "claim", id: "C7" },
      { kind: "text", text: " from the run " },
      { kind: "source", id: "S5" },
      { kind: "text", text: "; see " },
      { kind: "source", id: "S12" },
      { kind: "text", text: "." },
    ]);
    expect(segments("No markers here.")).toEqual([{ kind: "text", text: "No markers here." }]);
  });

  it("finds every claim of a real report in its text", () => {
    const text = DOCUMENT.sections.flatMap((section) => section.paragraphs).join(" ");
    const found = new Set(
      segments(text).flatMap((part) => (part.kind === "claim" ? [part.id] : [])),
    );
    expect([...found].sort()).toEqual(DOCUMENT.claims.map((claim) => claim.claim_id).sort());
  });

  it("links an official source, a page of the app and a file of the repository", () => {
    const filing = "https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/";
    expect(sourceLink(ref(filing, "sec_filing"))).toEqual({ kind: "external", href: filing });
    expect(sourceLink(ref("/data-catalog/sec-edgar", "data_source"))).toEqual({
      kind: "internal",
      href: "/data-catalog/sec-edgar",
    });
    expect(sourceLink(ref("docs/adr/0030-paired-monte-carlo.md"))).toEqual({
      kind: "external",
      href: `${REPOSITORY_BLOB}docs/adr/0030-paired-monte-carlo.md`,
    });
    expect(sourceLink(ref("fds-20261106-05c19bb5643a", "dataset"))).toEqual({ kind: "none" });
  });

  it("never links an unknown host or a path that leaves the repository", () => {
    expect(sourceLink(ref("https://evil.example/x", "sec_filing"))).toEqual({ kind: "none" });
    expect(sourceLink(ref("../secrets.md"))).toEqual({ kind: "none" });
    expect(sourceLink(ref("javascript:alert(1)"))).toEqual({ kind: "none" });
  });

  it("names downloads as the API does", () => {
    expect(downloadName(DOCUMENT, "markdown")).toBe(`${DOCUMENT.report_doc_id}.md`);
    expect(downloadName(DOCUMENT, "manifest")).toBe(`${DOCUMENT.report_doc_id}-manifest.json`);
  });
});
