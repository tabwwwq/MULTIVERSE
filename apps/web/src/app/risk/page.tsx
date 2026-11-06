import { SIMULATION_REPORT } from "@multiverse/contracts/simulation";
import { VALUATION_REPORT } from "@multiverse/contracts/valuation";
import type { Metadata } from "next";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { type Column, DataTable } from "@/components/ui/data-table";
import { ScenarioFigure } from "@/components/valuation/figures";
import { ScenarioWeights } from "@/components/valuation/scenario-weights";
import { StressDownload } from "@/components/valuation/stress-download";
import { PageHeader, Section } from "@/layouts/page-header";
import { formatValue } from "@/results/format";
import { SCENARIO_LABELS, driverText, percent, probabilityText } from "@/simulation/report";

export const metadata: Metadata = { title: "Risk Observatory" };

const report = VALUATION_REPORT;
const paths = SIMULATION_REPORT;
type Risk = (typeof paths.risks)[number];
type Scenario = (typeof report.scenarios)[number];
type Stress = (typeof report.stress)[number];

const usd = (value: string | null | undefined, signed = false) =>
  value === null || value === undefined
    ? "Undefined"
    : formatValue(Number(value), "usd", { signed });

const RISK_COLUMNS: ReadonlyArray<Column<Risk>> = [
  { key: "label", header: "Event within the horizon", rowHeader: true, wrap: true },
  { key: "scenario", header: "Scenario", render: (r) => SCENARIO_LABELS[r.scenario] },
  {
    key: "probability",
    header: "Share of paths, under the assumed model",
    numeric: true,
    render: probabilityText,
  },
];

const SCENARIO_COLUMNS: ReadonlyArray<Column<Scenario>> = [
  { key: "label", header: "Scenario", rowHeader: true },
  { key: "ev_p10", header: "EV p10", numeric: true, render: (r) => usd(r.ev_p10) },
  { key: "ev_p50", header: "EV p50", numeric: true, render: (r) => usd(r.ev_p50) },
  { key: "ev_p90", header: "EV p90", numeric: true, render: (r) => usd(r.ev_p90) },
  { key: "equity_p50", header: "Equity p50", numeric: true, render: (r) => usd(r.equity_p50) },
  {
    key: "covenant_probability",
    header: "Covenant breach",
    numeric: true,
    render: (r) => percent(r.covenant_probability),
  },
  {
    key: "shortfall_probability",
    header: "Funding shortfall",
    numeric: true,
    render: (r) => percent(r.shortfall_probability),
  },
];

const STRESS_COLUMNS: ReadonlyArray<Column<Stress>> = [
  { key: "label", header: "Stress", rowHeader: true, wrap: true },
  {
    key: "ev_change",
    header: "Change of EV",
    numeric: true,
    render: (r) => usd(r.ev_change, true),
  },
  { key: "lowest_cash", header: "Lowest cash", numeric: true, render: (r) => usd(r.lowest_cash) },
  {
    key: "peak_leverage",
    header: "Peak net debt / EBITDA",
    numeric: true,
    render: (r) => (r.peak_leverage === null ? "Undefined" : `${r.peak_leverage.toFixed(2)}x`),
  },
  {
    key: "lowest_interest_cover",
    header: "Lowest interest cover",
    numeric: true,
    render: (r) =>
      r.lowest_interest_cover === null ? "Undefined" : `${r.lowest_interest_cover.toFixed(1)}x`,
  },
  {
    key: "first_breach",
    header: "First covenant breach",
    render: (r) => r.first_breach ?? "None",
  },
  {
    key: "peak_shortfall",
    header: "Peak shortfall",
    numeric: true,
    render: (r) => usd(r.peak_shortfall),
  },
];

interface WorstRow {
  path: number;
  rank: number;
  ev_change: string;
  story: string;
}

const WORST_COLUMNS: ReadonlyArray<Column<WorstRow>> = [
  { key: "rank", header: "Rank", numeric: true, rowHeader: true },
  {
    key: "ev_change",
    header: "Paired change of EV",
    numeric: true,
    render: (r) => usd(r.ev_change, true),
  },
  { key: "story", header: "Drivers", wrap: true },
];

const worst: WorstRow[] = paths.tails.slice(0, 5).map((row) => ({
  path: row.path,
  rank: row.rank,
  ev_change: row.ev_change,
  story: row.drivers.map((driver) => `${driver.label}: ${driverText(driver)}`).join(". "),
}));

export default function RiskPage() {
  return (
    <>
      <PageHeader
        title="Risk Observatory"
        summary="Liquidity, credit and tail risks of the research case, in paths and in stress cases."
        meta={
          <>
            <Badge tone="warning">Under the assumed model</Badge>
            <Badge tone="violet">Hypothetical decision</Badge>
          </>
        }
      />
      <div className="mb-8 max-w-3xl">
        <Alert tone="warning" title={paths.probability_label}>
          Every share of paths here holds under the assumed model, and no calibration stands behind
          it. Stress cases are chosen, not forecast. The decision is invented, not a plan of{" "}
          {report.company_name}, and nothing here is advice.
        </Alert>
      </div>
      <Section
        id="probabilities"
        title="Credit and liquidity"
        intro={`${paths.result.paths} paired paths. The margin shown is two Monte Carlo errors: it says nothing about whether the model is right.`}
      >
        <DataTable
          id="risk-table"
          caption="Share of paths where each event happens at least once"
          columns={RISK_COLUMNS}
          rows={paths.risks}
          rowKey={(row) => `${row.risk}-${row.scenario}`}
        />
      </Section>
      <Section
        id="scenarios"
        title="Bear, base and bull"
        intro={`Each scenario moves the central growth and margin, then runs ${report.scenarios[0]?.paths ?? 0} paired paths on the same shocks. The moves are assumptions.`}
      >
        <figure className="max-w-3xl">
          <ScenarioFigure rows={report.scenarios} />
          <figcaption className="mt-1 text-small text-ink-muted">
            Enterprise value with the decision: p10 to p90, with the median marked.
          </figcaption>
        </figure>
        <div className="mt-4">
          <DataTable
            id="scenario-table"
            caption="Value and risks by scenario, in USD"
            columns={SCENARIO_COLUMNS}
            rows={report.scenarios}
            rowKey={(row) => row.scenario}
          />
        </div>
        <div className="mt-6 max-w-2xl">
          <ScenarioWeights rows={report.scenarios} />
        </div>
      </Section>
      <Section
        id="stress"
        title="Stress cases"
        intro="The central path with the decision, with one stress at a time and then all at once, through the full statements."
      >
        <DataTable
          id="stress-table"
          caption="What each stress does to value, liquidity and credit, in USD"
          columns={STRESS_COLUMNS}
          rows={report.stress}
          rowKey={(row) => row.key}
        />
        <div className="mt-3">
          <StressDownload report={report} />
        </div>
      </Section>
      <Section
        id="adverse"
        title={report.adverse_title}
        intro="Told from the statements of the stressed path: each sentence is a number of that path."
      >
        <ol className="max-w-3xl list-decimal pl-5 text-body text-ink">
          {report.adverse_story.map((step) => (
            <li key={step} className="mb-2">
              {step}
            </li>
          ))}
        </ol>
      </Section>
      <Section
        id="worst"
        title="Worst paths of the run"
        intro="The paths where the decision cost the most value, and what they were exposed to."
      >
        <DataTable
          id="worst-table"
          caption="Worst paths by paired change of EV"
          columns={WORST_COLUMNS}
          rows={worst}
          rowKey={(row) => String(row.path)}
        />
      </Section>
    </>
  );
}
