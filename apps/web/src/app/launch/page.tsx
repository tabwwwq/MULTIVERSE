import { SIMULATION_REPORT } from "@multiverse/contracts/simulation";
import type { Metadata } from "next";
import { DistributionFigure, EventTimeline } from "@/components/results/result-figures";
import { TimelineExplorer } from "@/components/results/timeline-explorer";
import { RunBoard } from "@/components/simulation/run-board";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { type Column, DataTable } from "@/components/ui/data-table";
import { PageHeader, Section } from "@/layouts/page-header";
import { formatValue } from "@/results/format";
import {
  ORIGIN_LABELS,
  SCENARIO_LABELS,
  VALUE_LABELS,
  convergenceSizes,
  driverText,
  originCounts,
  percent,
  probabilityText,
  settledShare,
} from "@/simulation/report";

export const metadata: Metadata = { title: "Launch Center" };

const report = SIMULATION_REPORT;
const { manifest, result, diagnostics } = report;
type Risk = (typeof report.risks)[number];
type Value = (typeof report.values)[number];
type Tail = (typeof report.tails)[number];
type Sensitivity = (typeof report.sensitivity)[number];
type Input = (typeof report.inputs)[number];

function usd(value: string | null | undefined, signed = false): string {
  return value === null || value === undefined
    ? "Undefined"
    : formatValue(Number(value), "usd", { signed });
}

const RISK_COLUMNS: ReadonlyArray<Column<Risk>> = [
  { key: "label", header: "Event within the horizon", rowHeader: true, render: (r) => r.label },
  { key: "scenario", header: "Scenario", render: (r) => SCENARIO_LABELS[r.scenario] },
  {
    key: "probability",
    header: "Share of paths, ± two Monte Carlo errors",
    numeric: true,
    render: probabilityText,
  },
];

const VALUE_COLUMNS: ReadonlyArray<Column<Value>> = [
  { key: "metric", header: "Value", rowHeader: true, render: (r) => VALUE_LABELS[r.metric] },
  { key: "scenario", header: "Scenario", render: (r) => SCENARIO_LABELS[r.scenario] },
  { key: "p1", header: "p1", numeric: true, render: (r) => usd(r.p1, r.metric === "ev_change") },
  { key: "p10", header: "p10", numeric: true, render: (r) => usd(r.p10, r.metric === "ev_change") },
  { key: "p50", header: "p50", numeric: true, render: (r) => usd(r.p50, r.metric === "ev_change") },
  { key: "p90", header: "p90", numeric: true, render: (r) => usd(r.p90, r.metric === "ev_change") },
  { key: "p99", header: "p99", numeric: true, render: (r) => usd(r.p99, r.metric === "ev_change") },
];

const TAIL_DRIVERS = ["growth_shock", "margin_shock", "rate_shift", "deal_closed"] as const;

interface TailView {
  path: number;
  rank: number;
  ev_change: string;
  growth_shock: string;
  margin_shock: string;
  rate_shift: string;
  deal_closed: string;
}

function tailView(row: Tail): TailView {
  const text = (name: (typeof TAIL_DRIVERS)[number]) => {
    const driver = row.drivers.find((item) => item.name === name);
    return driver ? driverText(driver) : "Unknown";
  };
  return {
    path: row.path,
    rank: row.rank,
    ev_change: usd(row.ev_change, true),
    growth_shock: text("growth_shock"),
    margin_shock: text("margin_shock"),
    rate_shift: text("rate_shift"),
    deal_closed: text("deal_closed"),
  };
}

const TAIL_COLUMNS: ReadonlyArray<Column<TailView>> = [
  { key: "rank", header: "Rank", numeric: true, rowHeader: true, render: (r) => r.rank },
  { key: "ev_change", header: "Paired change of EV", numeric: true, render: (r) => r.ev_change },
  ...TAIL_DRIVERS.map((name, index): Column<TailView> => ({
    key: name,
    header: report.tails[0]?.drivers[index]?.label ?? name,
    numeric: name !== "deal_closed",
    render: (row) => row[name],
  })),
];

const SENSITIVITY_COLUMNS: ReadonlyArray<Column<Sensitivity>> = [
  { key: "label", header: "Shock model", rowHeader: true, render: (r) => r.label },
  { key: "ebitda_p10", header: "EBITDA p10", numeric: true, render: (r) => usd(r.ebitda_p10) },
  { key: "ebitda_p50", header: "EBITDA p50", numeric: true, render: (r) => usd(r.ebitda_p50) },
  { key: "ebitda_p90", header: "EBITDA p90", numeric: true, render: (r) => usd(r.ebitda_p90) },
  {
    key: "ev_change_p50",
    header: "EV change p50",
    numeric: true,
    render: (r) => usd(r.ev_change_p50, true),
  },
  {
    key: "covenant_probability",
    header: "Covenant breach",
    numeric: true,
    render: (r) => percent(r.covenant_probability),
  },
];

const INPUT_COLUMNS: ReadonlyArray<Column<Input>> = [
  { key: "name", header: "Input", rowHeader: true, render: (r) => r.name.replaceAll("_", " ") },
  { key: "origin", header: "How it is known", render: (r) => ORIGIN_LABELS[r.origin] },
  { key: "note", header: "Note", render: (r) => r.note },
];

const CONVERGENCE_STATISTICS = [
  ...new Map(report.convergence.map((row) => [row.statistic, row.label])).entries(),
];

function ConvergenceTable() {
  const sizes = convergenceSizes(report);
  return (
    <div className="overflow-x-auto" role="region" aria-label="Convergence" tabIndex={0}>
      <table className="w-full text-small text-ink">
        <caption className="sr-only">Each statistic at each number of paths</caption>
        <thead>
          <tr className="border-b border-line text-left">
            <th scope="col" className="py-2 pr-4">
              Statistic
            </th>
            {sizes.map((size) => (
              <th key={size} scope="col" className="py-2 pr-4 text-right tabular-nums">
                {size} paths
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {CONVERGENCE_STATISTICS.map(([statistic, label]) => (
            <tr key={statistic} className="border-b border-line">
              <th scope="row" className="py-2 pr-4 text-left font-normal">
                {label}
              </th>
              {sizes.map((size) => {
                const row = report.convergence.find(
                  (item) => item.statistic === statistic && item.paths === size,
                );
                const value = statistic.endsWith("_probability")
                  ? percent(row?.value ?? 0)
                  : formatValue(row?.value ?? 0, "usd", { signed: statistic.startsWith("ev_") });
                return (
                  <td key={size} className="py-2 pr-4 text-right tabular-nums">
                    {value}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function LaunchPage() {
  const counts = originCounts(report);
  const sizes = convergenceSizes(report);
  const evChange = result.distributions.find((item) => item.metric === "ev");
  const decision = result.scenarios.find((run) => run.key === "alt_a")?.decision;
  return (
    <>
      <PageHeader
        title="Launch Center"
        summary="Data readiness, model version and cost before a run, and the first paired Monte Carlo run on a real company."
        meta={
          <>
            <Badge tone="warning">Conditional, not validated</Badge>
            <Badge tone="violet">Hypothetical decision</Badge>
          </>
        }
      />
      <div className="mb-8 flex max-w-3xl flex-col gap-3">
        <Alert tone="warning" title={report.probability_label}>
          <p>
            Bands are conditional model quantiles, not confidence intervals. Probabilities hold only
            under the assumed model: nothing here is calibrated against outcomes, and an 80% band
            carries no promise of containing 80% of what happens.
          </p>
          <p className="mt-2">
            The two paths of a pair share their shocks, which lowers the noise of the comparison. It
            does not show what the decision would truly do: its effects are assumptions, and no
            causal effect has been estimated. The decision is invented, not a plan of{" "}
            {result.company_name}. This is not advice.
          </p>
        </Alert>
      </div>
      <Section
        id="readiness"
        title="Readiness"
        intro="What this run stands on. Most of the balance sheet is not in the warehouse, so it is implied or assumed."
      >
        <dl className="mb-4 grid gap-3 text-small sm:grid-cols-2">
          <div>
            <dt className="text-ink-muted">Company and cutoff</dt>
            <dd className="text-ink">
              {result.company_name}, known at {result.as_of}
            </dd>
          </div>
          <div>
            <dt className="text-ink-muted">Data snapshot</dt>
            <dd className="text-ink">{manifest.dataset_id ?? "None"}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Model</dt>
            <dd className="text-ink">
              {manifest.model_id ?? "None"}: EBITDA margin at 4 and 8 quarters, research only
            </dd>
          </div>
          <div>
            <dt className="text-ink-muted">Inputs</dt>
            <dd className="text-ink">
              {counts.observed} observed, {counts.model} from the model, {counts.implied} implied,{" "}
              {counts.assumed} assumed
            </dd>
          </div>
          <div>
            <dt className="text-ink-muted">Shock model</dt>
            <dd className="text-ink">{manifest.shock_model}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Run</dt>
            <dd className="text-ink tabular-nums">
              {result.paths} paths, seed {result.seed}, {diagnostics.seconds} s
            </dd>
          </div>
        </dl>
        <details className="rounded-panel border border-line bg-surface p-4">
          <summary className="cursor-pointer font-medium text-ink">How each input is known</summary>
          <div className="mt-3">
            <DataTable
              id="inputs-table"
              caption="Inputs of the case"
              columns={INPUT_COLUMNS}
              rows={report.inputs}
              rowKey={(row) => row.name}
            />
          </div>
        </details>
      </Section>
      <Section
        id="paths"
        title="Paths"
        intro="Reported quarters, then p10 to p90 of the paths. Quarter by quarter, in the three statements of the finance engine."
      >
        <TimelineExplorer result={result} initialMetric="ebitda" initialMode="absolute" />
        <div className="mt-6">
          <EventTimeline events={result.events} />
        </div>
      </Section>
      <Section
        id="paired"
        title="Paired change"
        intro="Computed path by path, then summarized: the quantile of a difference is not the difference of quantiles."
      >
        <div className="flex max-w-xl flex-col gap-4">
          {evChange ? <DistributionFigure distribution={evChange} result={result} /> : null}
        </div>
        <div className="mt-4">
          <DataTable
            id="values-table"
            caption="Enterprise and equity value across paths, in USD. A model number, not a market value."
            columns={VALUE_COLUMNS}
            rows={report.values}
            rowKey={(row) => `${row.metric}-${row.scenario}`}
          />
        </div>
      </Section>
      <Section
        id="risks"
        title="Risks"
        intro={`${report.probability_label}. The error shown is Monte Carlo error only: it says nothing about whether the model is right.`}
      >
        <DataTable
          id="risks-table"
          caption="Share of paths where each event happens at least once"
          columns={RISK_COLUMNS}
          rows={report.risks}
          rowKey={(row) => `${row.risk}-${row.scenario}`}
        />
      </Section>
      <Section
        id="tails"
        title="Worst paths"
        intro="The ten paths where the decision cost the most value, and what they were exposed to."
      >
        <DataTable
          id="tails-table"
          caption="Worst paths by paired change of EV"
          columns={TAIL_COLUMNS}
          rows={report.tails.map(tailView)}
          rowKey={(row) => String(row.path)}
        />
      </Section>
      <Section
        id="convergence"
        title="Convergence"
        intro={`The first paths of a run are a shorter run. At ${sizes[0]} paths, ${percent(settledShare(report, sizes[0] ?? 0), 0)} of the statistics already lie within two errors of the longest run.`}
      >
        <ConvergenceTable />
      </Section>
      <Section
        id="sensitivity"
        title="Sensitivity to the shock model"
        intro={`The same decision with one choice changed, ${report.sensitivity[0]?.paths ?? 0} paths each.`}
      >
        <DataTable
          id="sensitivity-table"
          caption="EBITDA of the last quarter with the decision, by choice of shock model"
          columns={SENSITIVITY_COLUMNS}
          rows={report.sensitivity}
          rowKey={(row) => row.variant}
        />
      </Section>
      <Section
        id="diagnostics"
        title="Diagnostics"
        intro="Every statement path passed the reconciliation of the finance engine, or the run would have stopped."
      >
        <ul className="list-disc pl-5 text-small text-ink">
          <li>{diagnostics.path_identities_checked} statement paths reconciled to the cent.</li>
          <li>
            {diagnostics.redraws} paths drawn again; bounds met in{" "}
            {percent(diagnostics.clipped_share, 2)} of quarters; value undefined on{" "}
            {percent(diagnostics.ev_undefined_share, 2)} of paths.
          </li>
          <li>
            Sector growth and margin correlate at {diagnostics.historical_correlation} in the
            history and {diagnostics.simulated_correlation} in the draw.
          </li>
          <li>
            {diagnostics.history_quarters} quarters of history feed the shocks, so no run can show a
            crisis unlike those quarters, however many paths it has.
          </li>
          {diagnostics.flags.map((flag) => (
            <li key={flag}>{flag}</li>
          ))}
        </ul>
        <p className="mt-3 text-small text-ink-muted">
          Report <code>{manifest.report_id}</code>, finance {manifest.finance_version}, simulation{" "}
          {manifest.simulation_version}, contracts {manifest.contracts_version}, code{" "}
          {manifest.code_version}.
        </p>
      </Section>
      <Section
        id="run"
        title="Start a run"
        intro="Every run goes through the queue: it needs an approved estimate, and stops at a batch of paths."
      >
        {decision ? <RunBoard caseId={manifest.case_id} decision={decision} /> : null}
      </Section>
    </>
  );
}
