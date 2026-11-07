import type { ResearchReport, SourceRef } from "@multiverse/contracts";
import { safeExternalUrl } from "@/lib/safe-url";

/*
 * Report Studio on screen (Stage 25): the document as the worker wrote it. Nothing is
 * recomputed here; the page only turns claim and source markers into links.
 */

export const REPOSITORY_BLOB = "https://github.com/tabwwwq/MULTIVERSE/blob/main/";

export type Segment =
  { kind: "text"; text: string } | { kind: "claim"; id: string } | { kind: "source"; id: string };

const MARKER = /\[(C\d{1,3})\]|\((S\d{1,3})\)|\b(S\d{1,3})\b/g;

/** A paragraph cut into plain text, claim markers `[C3]` and source references `S2`. */
export function segments(text: string): Segment[] {
  const found: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    const at = match.index ?? 0;
    if (at > last) found.push({ kind: "text", text: text.slice(last, at) });
    const [whole, claim, inParentheses, bare] = match;
    if (claim) found.push({ kind: "claim", id: claim });
    else found.push({ kind: "source", id: (inParentheses ?? bare) as string });
    last = at + whole.length;
  }
  if (last < text.length) found.push({ kind: "text", text: text.slice(last) });
  return found;
}

export type SourceLink = { kind: "external" | "internal"; href: string } | { kind: "none" };

/** Where a source points: an official site, a page of this app, a file of the repository. */
export function sourceLink(ref: SourceRef): SourceLink {
  if (ref.target.startsWith("https://")) {
    const href = safeExternalUrl(ref.target);
    return href ? { kind: "external", href } : { kind: "none" };
  }
  if (ref.target.startsWith("/data-catalog/")) return { kind: "internal", href: ref.target };
  if (/^(docs|packages|data|apps|services|pipelines)\/[\w./-]+$/.test(ref.target)) {
    return { kind: "external", href: `${REPOSITORY_BLOB}${ref.target}` };
  }
  return { kind: "none" };
}

/** The file name a download should get, as the API names it. */
export function downloadName(
  report: ResearchReport,
  part: "markdown" | "csv" | "manifest",
): string {
  if (part === "markdown") return `${report.report_doc_id}.md`;
  if (part === "csv") return `${report.report_doc_id}.csv`;
  return `${report.report_doc_id}-manifest.json`;
}
