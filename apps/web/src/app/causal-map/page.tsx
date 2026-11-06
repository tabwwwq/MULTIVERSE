import { CAUSAL_STUDY, type TreatmentStudy } from "@multiverse/contracts/causal";
import type { Metadata } from "next";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { type Column, DataTable } from "@/components/ui/data-table";
import { METHOD_LABELS, POSITIONS, feasibleCount, growthRow } from "@/causal/study";
import { TYPE_LABELS } from "@/events/registry";
import { PageHeader, Section } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Causal Map" };

const { graph } = CAUSAL_STUDY;

function share(value: number | null | undefined): string {
  return value === null || value === undefined ? "Unknown" : `${Math.round(100 * value)}%`;
}

const COLUMNS: ReadonlyArray<Column<TreatmentStudy>> = [
  {
    key: "treatment",
    header: "Decision",
    rowHeader: true,
    render: (row) => TYPE_LABELS[row.treatment],
  },
  {
    key: "usable",
    header: "Usable events",
    numeric: true,
    render: (r) => `${r.usable} of ${r.events}`,
  },
  { key: "support", header: "Support", numeric: true, render: (r) => share(r.support) },
  {
    key: "near_decision_share",
    header: "Another decision within a year",
    numeric: true,
    render: (r) => share(r.near_decision_share),
  },
  {
    key: "null",
    header: "Smallest growth effect detectable today",
    numeric: true,
    render: (r) => growthRow(r)?.minimum_effect_now.toFixed(2) ?? "Unknown",
  },
  {
    key: "candidate_pool",
    header: "With every candidate read",
    numeric: true,
    render: (r) => growthRow(r)?.minimum_effect_pool.toFixed(2) ?? "Unknown",
  },
  {
    key: "verdicts",
    header: "Methods feasible",
    numeric: true,
    render: (r) => `${feasibleCount(r)} of ${r.verdicts.length}`,
  },
];

function Graph() {
  const place = (id: string) => POSITIONS[id] ?? { x: 0, y: 0 };
  return (
    <figure>
      <svg
        viewBox="0 0 760 340"
        role="img"
        aria-label="Hypothesised causes of a corporate decision and its outcomes, with unobserved expectations"
        className="w-full rounded-panel border border-line bg-surface"
      >
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" className="fill-ink-muted" />
          </marker>
        </defs>
        {graph.edges.map((edge) => {
          const from = place(edge.source);
          const to = place(edge.target);
          return (
            <line
              key={`${edge.source}-${edge.target}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              markerEnd="url(#arrow)"
              className="stroke-line-strong"
            />
          );
        })}
        {graph.nodes.map((node) => {
          const { x, y } = place(node.node_id);
          return (
            <g key={node.node_id}>
              <rect
                x={x - 72}
                y={y - 19}
                width={144}
                height={38}
                rx={8}
                strokeDasharray={node.observed ? undefined : "5 4"}
                className="fill-canvas stroke-line-strong"
              />
              <text x={x} y={y + 4} textAnchor="middle" className="fill-ink text-[11px]">
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-2 text-small text-ink-muted">
        A hypothesis drawn from reasoning, not found in data. Dashed boxes are not observed.
      </figcaption>
    </figure>
  );
}

export default function CausalMapPage() {
  return (
    <>
      <PageHeader
        title="Causal Map"
        summary="What would have to hold to say that a decision caused an outcome, and how far the data are from that."
        meta={<Badge tone="warning">Feasibility study, no effect estimated</Badge>}
      />
      <Section id="status" title="What this page does not say">
        <Alert tone="warning" title="No effect is estimated here">
          No outcome after a decision was read, and no method is feasible yet. Nothing on this page
          says what a decision did to a company.
          <ul className="mt-2 list-disc pl-5">
            {CAUSAL_STUDY.audit_blockers.slice(-2).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Alert>
      </Section>
      <Section id="graph" title="The assumed graph">
        <Graph />
        <details className="mt-4">
          <summary className="cursor-pointer text-small text-ink-muted">
            The graph in words, and what it leaves out
          </summary>
          <ul className="mt-2 flex flex-col gap-1 text-small text-ink-muted">
            {graph.edges.map((edge) => (
              <li key={`${edge.source}-${edge.target}`}>
                {edge.source} to {edge.target}: {edge.rationale}
              </li>
            ))}
            {graph.omitted.map((line) => (
              <li key={line}>Left out: {line}</li>
            ))}
          </ul>
        </details>
      </Section>
      <Section
        id="feasibility"
        title="Feasibility by decision"
        intro="Measured before and around the decisions, never after them. Growth effects are in the units of symmetric growth."
      >
        <DataTable
          id="feasibility-table"
          caption="What each decision could support today"
          columns={COLUMNS}
          rows={CAUSAL_STUDY.treatments}
          rowKey={(row) => row.treatment}
        />
      </Section>
      <Section id="methods" title="Why each method is closed">
        <div className="flex flex-col gap-3">
          {CAUSAL_STUDY.treatments.map((row) => (
            <details
              key={row.treatment}
              className="rounded-panel border border-line bg-surface p-4"
            >
              <summary className="cursor-pointer font-medium text-ink">
                {TYPE_LABELS[row.treatment]}
              </summary>
              <p className="mt-2 text-small text-ink-muted">{row.estimand}</p>
              <ul className="mt-2 flex flex-col gap-2 text-small text-ink-muted">
                {row.verdicts.map((verdict) => (
                  <li key={verdict.method}>
                    <span className="text-ink">{METHOD_LABELS[verdict.method]}:</span>{" "}
                    {verdict.feasible
                      ? "feasible"
                      : verdict.reasons.slice(1).join(" ") || "blocked by the audit."}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-small text-ink-muted">
                Never testable here: {row.untested[0]}
              </p>
            </details>
          ))}
        </div>
      </Section>
    </>
  );
}
