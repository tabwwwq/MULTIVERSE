"use client";

import type { SimulationReport } from "@multiverse/contracts";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { TimelineExplorer } from "@/components/results/timeline-explorer";
import { RunSummary } from "@/components/simulation/run-summary";
import { Alert } from "@/components/ui/alert";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Section } from "@/layouts/page-header";
import { fetchReport } from "@/models/jobs";
import { formatValue } from "@/results/format";
import { SCENARIO_LABELS, VALUE_LABELS, probabilityText } from "@/simulation/report";

type Risk = SimulationReport["risks"][number];
type Value = SimulationReport["values"][number];

function usd(value: string | null | undefined, signed = false): string {
  return value === null || value === undefined
    ? "Undefined"
    : formatValue(Number(value), "usd", { signed });
}

const RISKS: ReadonlyArray<Column<Risk>> = [
  { key: "label", header: "Event within the horizon", rowHeader: true, render: (r) => r.label },
  { key: "scenario", header: "Scenario", render: (r) => SCENARIO_LABELS[r.scenario] },
  {
    key: "probability",
    header: "Share of paths, ± two Monte Carlo errors",
    numeric: true,
    render: probabilityText,
  },
];

const VALUES: ReadonlyArray<Column<Value>> = [
  { key: "metric", header: "Value", rowHeader: true, render: (v) => VALUE_LABELS[v.metric] },
  { key: "scenario", header: "Scenario", render: (v) => SCENARIO_LABELS[v.scenario] },
  { key: "p10", header: "p10", numeric: true, render: (v) => usd(v.p10) },
  { key: "p50", header: "p50", numeric: true, render: (v) => usd(v.p50) },
  { key: "p90", header: "p90", numeric: true, render: (v) => usd(v.p90) },
];

type Load =
  | { state: "loading" }
  | { state: "ready"; report: SimulationReport }
  | { state: "failed"; message: string };

/** The stored report of a run, read from the API of this computer. */
export function RunReport() {
  const job = useSearchParams().get("job");
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    if (!job || !/^job-[0-9a-f]{12}$/.test(job)) return undefined;
    const controller = new AbortController();
    fetchReport(job, controller.signal)
      .then((report) => setLoad({ state: "ready", report }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : "The service did not answer.";
        setLoad({ state: "failed", message });
      });
    return () => controller.abort();
  }, [job]);

  if (!job || !/^job-[0-9a-f]{12}$/.test(job)) {
    return (
      <Alert tone="info" title="No run chosen">
        Start one in the <Link href="/decisions">Decision Builder</Link>.
      </Alert>
    );
  }
  if (load.state === "loading") {
    return <p className="text-body text-ink-muted">Reading the result.</p>;
  }
  if (load.state === "failed") {
    return (
      <Alert tone="warning" title="This result cannot be read">
        {load.message} Results live on this computer: start the engine with <code>npm run app</code>
        .
      </Alert>
    );
  }
  const { report } = load;
  return (
    <div className="flex flex-col gap-10">
      <Alert tone="warning" title={report.probability_label}>
        {report.result.title}. {report.manifest.settings.paths.toLocaleString("en-US")} paths. Most
        inputs of a case are assumed, and each says so in the case. This is not a forecast of what
        will happen, and not advice.
      </Alert>
      <RunSummary report={report} />
      <Section id="paths" title="Paths">
        <TimelineExplorer result={report.result} initialMetric="revenue" initialMode="absolute" />
      </Section>
      <Section id="values" title="Value">
        <DataTable
          id="run-values"
          columns={VALUES}
          rows={report.values}
          rowKey={(row) => `${row.metric}-${row.scenario}`}
          caption="Model values, USD"
        />
      </Section>
      <Section id="risks" title="Risks">
        <DataTable
          id="run-risks"
          columns={RISKS}
          rows={report.risks}
          rowKey={(row) => `${row.risk}-${row.scenario}`}
          caption="Share of paths with each event"
        />
      </Section>
    </div>
  );
}
