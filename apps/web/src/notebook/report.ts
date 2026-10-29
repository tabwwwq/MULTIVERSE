import type {
  ReportSnapshot,
  ReproducibilityManifest,
  ScenarioRecord,
  ScenarioRevision,
} from "@multiverse/contracts";
import type { Distribution } from "@multiverse/contracts/interventions";
import { formatMagnitude, specFor, unitSpecFor } from "@/decisions/catalog";
import { formatValue } from "@/decisions/units";
import type { Clock, CompanyNames } from "@/notebook/model";

/*
 * Markdown report of one revision with its reproducibility manifest (PRD FR-RP-01,
 * FR-RP-02, FR-RP-04). The content depends only on the revision, so exporting the same
 * revision twice gives the same text and manifest (US-12); each export is still its own
 * snapshot with its own ID, and the earlier one is never replaced (FR-RP-03).
 */

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function manifestFor(
  record: ScenarioRecord,
  revision: ScenarioRevision,
): ReproducibilityManifest {
  return {
    contracts_version: revision.draft.contracts_version,
    scenario_id: record.scenario_id,
    revision: revision.revision,
    mode: revision.mode,
    data_origin: revision.draft.data_origin,
    causal_status: "not_assessed",
    as_of: `${revision.draft.as_of}T23:59:59Z`,
    seed: revision.draft.seed,
    // The deployed build will record its commit (Stage 26); local builds have none.
    code_version: "unversioned",
    dataset_snapshot_id: null,
    model_id: null,
    source_ids: [],
    generated_at: revision.created_at,
  };
}

function distributionText(
  distribution: Distribution,
  unit: Parameters<typeof formatValue>[1],
): string {
  if (distribution.shape === "fixed") return formatValue(distribution.value, unit);
  if (distribution.shape === "uniform") {
    return `uniform ${formatValue(distribution.low, unit)} to ${formatValue(distribution.high, unit)}`;
  }
  return `triangular ${formatValue(distribution.low, unit)} to ${formatValue(distribution.high, unit)}, most likely ${formatValue(distribution.mode, unit)}`;
}

function escapeCell(text: string): string {
  return text.replaceAll("|", "\\|").replaceAll("\n", " ");
}

/** Parameter rows of a decision, in catalog order, with units. */
export function decisionRows(revision: ScenarioRevision): [string, string][] {
  const { decision } = revision.draft;
  const spec = specFor(decision.type);
  const record = decision as unknown as Record<string, unknown>;
  const unit = unitSpecFor(spec, decision.magnitude.unit);
  const rows: [string, string][] = [
    ["Decision", spec.label],
    [
      spec.magnitude.label,
      unit ? formatMagnitude(decision.magnitude.value, unit) : decision.magnitude.value,
    ],
    ["Announced on", decision.timing.announcement_date],
    ["Takes effect on", decision.timing.effective_date],
    ["Lag", `${decision.timing.lag_quarters} quarters`],
    ["Ramp to full effect", `${decision.timing.ramp_quarters} quarters`],
  ];
  for (const parameter of spec.parameters) {
    const value = record[parameter.key];
    rows.push([
      parameter.label,
      parameter.uncertain
        ? distributionText(value as Distribution, parameter.unit)
        : formatValue(String(value), parameter.unit),
    ]);
  }
  if (spec.share_group) {
    const shares = record[spec.share_group.key] as Record<string, string>;
    rows.push([
      spec.share_group.label,
      spec.share_group.members
        .map((member) => `${member.label} ${formatValue(shares[member.key] ?? "0", "fraction")}`)
        .join(", "),
    ]);
  }
  return rows;
}

function slug(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "scenario"
  );
}

export function reportFileName(record: ScenarioRecord, revision: ScenarioRevision): string {
  const demo = revision.draft.data_origin === "synthetic" ? "_DEMO" : "";
  return `multiverse_${slug(record.name)}_r${revision.revision}${demo}.md`;
}

export function reportMarkdown(
  record: ScenarioRecord,
  revision: ScenarioRevision,
  companies: CompanyNames,
): string {
  const { draft } = revision;
  const company = companies[draft.company_id];
  const manifest = manifestFor(record, revision);
  const lines = [
    "> SYNTHETIC DEMO DATA. The company and its figures are fictional and no model was run. This is not investment advice.",
    "",
    `# ${record.name} (revision ${revision.revision})`,
    "",
    `- Company: ${company ? `${company.name}${company.ticker ? ` (${company.ticker})` : ""}` : "unknown"}, ID ${draft.company_id}`,
    `- Knowledge cutoff: ${draft.as_of}`,
    `- Horizon: ${draft.horizon_quarters} quarters`,
    `- Seed: ${draft.seed}`,
    "- Currency: USD",
    "- Mode: Demo (synthetic data)",
    `- Result status: ${revision.result_status === "not_run" ? "not run (the simulation engine arrives in Stage 22)" : revision.result_status}`,
    `- Revision created: ${revision.created_at}${revision.parent_revision ? `, edited from revision ${revision.parent_revision}` : ""}`,
    ...(revision.derived_from
      ? [
          `- Duplicated from scenario ${revision.derived_from.scenario_id}, revision ${revision.derived_from.revision}`,
        ]
      : []),
    `- Tags: ${record.tags.length > 0 ? record.tags.join(", ") : "none"}`,
    "",
    "## Decision",
    "",
    "| Parameter | Value |",
    "|---|---|",
    ...decisionRows(revision).map(
      ([label, value]) => `| ${escapeCell(label)} | ${escapeCell(value)} |`,
    ),
    "",
    "## Sensitivity",
    "",
    draft.sensitivity.parameters.length > 0
      ? `One at a time over ${draft.sensitivity.parameters.join(", ")}, ${draft.sensitivity.points} points each.`
      : "None chosen.",
    "",
    "## Notes",
    "",
    record.notes.trim() === "" ? "No notes." : record.notes.trim(),
    "",
    "## What this does not mean",
    "",
    "- Nothing here is a forecast: no model was run for this revision.",
    "- Defaults marked placeholder are not estimates.",
    "- A scenario is not a causal claim about what the company would have earned.",
    "",
    "## Reproducibility manifest",
    "",
    "```json",
    JSON.stringify(manifest, null, 2),
    "```",
    "",
  ];
  return lines.join("\n");
}

export async function buildReport(
  record: ScenarioRecord,
  revision: ScenarioRevision,
  companies: CompanyNames,
  clock: Clock,
): Promise<ReportSnapshot> {
  const content = reportMarkdown(record, revision, companies);
  return {
    report_id: clock.id(),
    source: { scenario_id: record.scenario_id, revision: revision.revision },
    created_at: clock.now(),
    format: "markdown",
    file_name: reportFileName(record, revision),
    content,
    content_sha256: await sha256Hex(content),
    manifest: manifestFor(record, revision),
  };
}
