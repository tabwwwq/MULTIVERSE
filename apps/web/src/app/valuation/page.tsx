import { VALUATION_REPORT } from "@multiverse/contracts/valuation";
import type { Metadata } from "next";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { type Column, DataTable } from "@/components/ui/data-table";
import { TornadoFigure } from "@/components/valuation/figures";
import { Workbench } from "@/components/valuation/workbench";
import { PageHeader, Section } from "@/layouts/page-header";
import { formatValue } from "@/results/format";
import { ORIGIN_LABELS } from "@/simulation/report";

export const metadata: Metadata = { title: "Valuation Studio" };

const report = VALUATION_REPORT;
const { manifest } = report;
const base = Number(report.base_value);
const withDecision = report.views.find((view) => view.scenario === "alt_a");
type Tornado = (typeof report.tornado)[number];
type Debt = NonNullable<typeof withDecision>["debt"][number];
type Check = (typeof report.checks)[number];
type Input = (typeof report.case_inputs)[number];

const usd = (value: string | number, signed = false) =>
  formatValue(Number(value), "usd", { signed });

const TORNADO_COLUMNS: ReadonlyArray<Column<Tornado>> = [
  { key: "label", header: "Driver", rowHeader: true },
  { key: "low_label", header: "Adverse setting" },
  {
    key: "low_value",
    header: "Change of EV",
    numeric: true,
    render: (row) => usd(Number(row.low_value) - base, true),
  },
  { key: "high_label", header: "Favourable setting" },
  {
    key: "high_value",
    header: "Change of EV",
    numeric: true,
    render: (row) => usd(Number(row.high_value) - base, true),
  },
];

const DEBT_COLUMNS: ReadonlyArray<Column<Debt>> = [
  { key: "label", header: "Quarter", rowHeader: true },
  { key: "term_debt", header: "Term debt", numeric: true, render: (r) => usd(r.term_debt) },
  { key: "revolver", header: "Revolver", numeric: true, render: (r) => usd(r.revolver) },
  { key: "cash", header: "Cash", numeric: true, render: (r) => usd(r.cash) },
  { key: "net_debt", header: "Net debt", numeric: true, render: (r) => usd(r.net_debt) },
  {
    key: "leverage",
    header: "Net debt / EBITDA",
    numeric: true,
    render: (r) => (r.leverage === null ? "Undefined" : `${r.leverage.toFixed(2)}x`),
  },
  {
    key: "interest_cover",
    header: "Interest cover",
    numeric: true,
    render: (r) => (r.interest_cover === null ? "Undefined" : `${r.interest_cover.toFixed(1)}x`),
  },
];

const CHECK_COLUMNS: ReadonlyArray<Column<Check>> = [
  { key: "label", header: "Check", rowHeader: true },
  {
    key: "passed",
    header: "Result",
    render: (r) => (r.passed ? "Passed" : r.key.startsWith("must_") ? "Failed" : "Warning"),
  },
  { key: "detail", header: "Detail", wrap: true },
];

const INPUT_COLUMNS: ReadonlyArray<Column<Input>> = [
  { key: "name", header: "Input", rowHeader: true, render: (r) => r.name.replaceAll("_", " ") },
  { key: "origin", header: "How it is known", render: (r) => ORIGIN_LABELS[r.origin] },
  { key: "note", header: "Note", wrap: true },
];

const yearEnds = (withDecision?.debt ?? []).filter(
  (_, index, rows) => (rows.length - 1 - index) % 4 === 0,
);

export default function ValuationPage() {
  return (
    <>
      <PageHeader
        title="Valuation Studio"
        summary="DCF on free cash flow to the firm, with enterprise value and equity value kept apart, for the research case of the Launch Center."
        meta={
          <>
            <Badge tone="warning">{report.value_label}</Badge>
            <Badge tone="violet">Hypothetical decision</Badge>
          </>
        }
      />
      <div className="mb-8 max-w-3xl">
        <Alert tone="warning" title={report.value_label}>
          <p>
            These numbers follow from the assumptions below, most of them not observed. They are not
            a market price, a fair value or advice about {report.company_name}. The decision is
            invented. Price per share is not shown: it needs corporate actions and market data this
            project does not hold (D-06).
          </p>
        </Alert>
      </div>
      <Section
        id="workbench"
        title="Parameters and value"
        intro="Change a parameter and the discounting is redone here, on statements the finance engine has reconciled. Changing the debt in the bridge does not redo the statements."
      >
        <Workbench report={report} />
      </Section>
      <Section
        id="tornado"
        title="What moves the value"
        intro={`${report.sensitivity_label}. Each driver moves alone on the central path with the decision, through the full statements.`}
      >
        <figure className="max-w-3xl">
          <TornadoFigure rows={report.tornado} base={base} />
          <figcaption className="sr-only">Tornado of enterprise value by driver</figcaption>
        </figure>
        <div className="mt-4">
          <DataTable
            id="tornado-table"
            caption="Change of enterprise value at each setting, in USD"
            columns={TORNADO_COLUMNS}
            rows={report.tornado}
            rowKey={(row) => row.driver}
          />
        </div>
      </Section>
      <Section
        id="debt"
        title="Debt schedule"
        intro="Year ends of the central path with the decision. Debt with no known maturity rolls."
      >
        <DataTable
          id="debt-table"
          caption="Debt, cash and credit ratios, in USD"
          columns={DEBT_COLUMNS}
          rows={yearEnds}
          rowKey={(row) => row.label}
        />
      </Section>
      <Section
        id="method"
        title="Method and assumptions"
        intro="How the value is built, and what it rests on."
      >
        <ul className="mb-4 list-disc pl-5 text-small text-ink">
          <li>
            FCFF = EBIT − tax on EBIT + D&amp;A − CAPEX − ΔNWC, with the price of deals in their
            quarter.
          </li>
          <li>
            Discounting at WACC from an effective annual rate: a quarter is (1 + r)^(−1/4), not r /
            4.
          </li>
          <li>
            Perpetual growth repeats the recurring FCFF of the last four quarters, growing yearly.
          </li>
          <li>Exit multiple applies to EBITDA before one-off items of the last four quarters.</li>
          <li>
            Equity value = EV − debt + cash − other senior claims + non-operating assets, at the
            balance date {report.balance_date}.
          </li>
          <li>WACC stays constant, whatever the decision does to debt and risk.</li>
        </ul>
        <details className="rounded-panel border border-line bg-surface p-4">
          <summary className="cursor-pointer font-medium text-ink">How each input is known</summary>
          <div className="mt-3">
            <DataTable
              id="valuation-inputs"
              caption="Inputs of the case"
              columns={INPUT_COLUMNS}
              rows={report.case_inputs}
              rowKey={(row) => row.name}
            />
          </div>
        </details>
      </Section>
      <Section
        id="quality"
        title="Quality protocol"
        intro="Required checks must pass or no report is written. A warning is a fact about this value that a reader should weigh."
      >
        <DataTable
          id="quality-table"
          caption="Checks of this report"
          columns={CHECK_COLUMNS}
          rows={report.checks}
          rowKey={(row) => row.key}
        />
        <p className="mt-3 text-small text-ink-muted">
          Report <code>{manifest.valuation_id}</code> from run{" "}
          <code>{manifest.simulation_report_id}</code>, finance {manifest.finance_version},
          simulation {manifest.simulation_version}, contracts {manifest.contracts_version}, code{" "}
          {manifest.code_version}.
        </p>
      </Section>
    </>
  );
}
