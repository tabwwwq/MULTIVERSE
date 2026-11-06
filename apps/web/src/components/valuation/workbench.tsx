"use client";

import type { ValuationReport } from "@multiverse/contracts";
import { useId, useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { SelectField, TextField } from "@/components/ui/field";
import { BridgeFigure, CompositionBar } from "@/components/valuation/figures";
import { downloadText } from "@/lib/download";
import { formatValue } from "@/results/format";
import {
  type Cell,
  type Inputs,
  type Line,
  type Method,
  dcfCsv,
  defaultInputs,
  matrix,
  matrixCsv,
  valuate,
  yearly,
} from "@/valuation/dcf";

type Unit = "percent" | "plain" | "usd_m" | "shares_m";
type NumberKey = Exclude<keyof Inputs, "method" | "ebitTax" | "dilutedShares">;

interface FieldSpec {
  key: NumberKey | "ebitTax" | "dilutedShares";
  label: string;
  unit: Unit;
  hint?: string;
}

const GROUPS: readonly { title: string; fields: readonly FieldSpec[] }[] = [
  {
    title: "WACC",
    fields: [
      { key: "riskFree", label: "Risk-free rate, %", unit: "percent" },
      { key: "equityRiskPremium", label: "Equity risk premium, %", unit: "percent" },
      { key: "beta", label: "Beta", unit: "plain" },
      { key: "costOfDebt", label: "Pre-tax cost of debt, %", unit: "percent" },
      { key: "capitalTax", label: "Tax rate in WACC, %", unit: "percent" },
      { key: "debtWeight", label: "Debt weight, %", unit: "percent" },
    ],
  },
  {
    title: "Forecast",
    fields: [
      {
        key: "fcffScale",
        label: "Projected operating FCFF, % of the statements",
        unit: "percent",
      },
      {
        key: "ebitTax",
        label: "Tax on EBIT, %",
        unit: "percent",
        hint: "Empty keeps the tax of the statements, with their carried losses.",
      },
    ],
  },
  {
    title: "Bridge at the balance date",
    fields: [
      { key: "debt", label: "Debt, USD million", unit: "usd_m" },
      { key: "cash", label: "Cash, USD million", unit: "usd_m" },
      { key: "otherClaims", label: "Other senior claims, USD million", unit: "usd_m" },
      { key: "nonOperating", label: "Non-operating assets, USD million", unit: "usd_m" },
    ],
  },
  {
    title: "Dilution",
    fields: [
      { key: "dilutedShares", label: "Diluted shares, million", unit: "shares_m" },
      {
        key: "newShares",
        label: "New shares at no consideration, million",
        unit: "shares_m",
        hint: "Gives a share of equity value, never a price (D-06).",
      },
    ],
  },
];

const SCALE: Record<Unit, number> = { percent: 100, plain: 1, usd_m: 1e-6, shares_m: 1e-6 };

function toText(value: number | null, unit: Unit): string {
  if (value === null) return "";
  return String(Number((value * SCALE[unit]).toFixed(4)));
}

function fromText(text: string, unit: Unit): number {
  return text.trim() === "" ? Number.NaN : Number(text) / SCALE[unit];
}

const usd = (value: number | null, signed = false) =>
  value === null ? "Undefined" : formatValue(value, "usd", { signed });
const percent = (value: number | null, digits = 1) =>
  value === null ? "Undefined" : `${(value * 100).toFixed(digits)}%`;

const QUARTER_COLUMNS: ReadonlyArray<Column<Line>> = [
  { key: "label", header: "Quarter", rowHeader: true },
  { key: "fcff", header: "FCFF", numeric: true, render: (r) => usd(r.fcff, true) },
  { key: "factor", header: "Discount factor", numeric: true, render: (r) => r.factor.toFixed(4) },
  { key: "present", header: "Present value", numeric: true, render: (r) => usd(r.present, true) },
];

type YearRow = ReturnType<typeof yearly>[number];

const YEAR_COLUMNS: ReadonlyArray<Column<YearRow>> = [
  { key: "label", header: "Year", rowHeader: true },
  { key: "fcff", header: "FCFF", numeric: true, render: (r) => usd(r.fcff, true) },
  { key: "present", header: "Present value", numeric: true, render: (r) => usd(r.present, true) },
];

function shade(value: number | null, low: number, high: number): string | undefined {
  if (value === null || high <= low) return undefined;
  const level = Math.round(((value - low) / (high - low)) * 34);
  return `color-mix(in oklab, var(--color-series-alt-a) ${level}%, transparent)`;
}

function Matrix({ cells }: { cells: readonly Cell[][] }) {
  const values = cells
    .flat()
    .flatMap((item) => (item.enterprise === null ? [] : [item.enterprise]));
  const low = Math.min(...values);
  const high = Math.max(...values);
  return (
    <div className="overflow-x-auto" role="region" aria-label="Sensitivity matrix" tabIndex={0}>
      <table className="w-full text-small text-ink tabular-nums">
        <caption className="sr-only">
          Enterprise value by WACC, in rows, and terminal growth, in columns
        </caption>
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className="p-2 text-left font-normal text-ink-muted">
              WACC \ g
            </th>
            {(cells[0] ?? []).map((item) => (
              <th key={item.growth} scope="col" className="p-2 text-right font-medium">
                {percent(item.growth, 2)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cells.map((row) => (
            <tr key={row[0]?.wacc} className="border-b border-line">
              <th scope="row" className="p-2 text-left font-medium">
                {percent(row[0]?.wacc ?? null, 2)}
              </th>
              {row.map((item) => (
                <td
                  key={item.growth}
                  className="p-2 text-right"
                  style={{ background: shade(item.enterprise, low, high) }}
                >
                  {item.enterprise === null ? "No value" : usd(item.enterprise)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Parameters on the left, what they give on the right. Nothing here leaves the browser. */
export function Workbench({ report }: { report: ValuationReport }) {
  const [viewIndex, setViewIndex] = useState(1);
  const view = report.views[viewIndex] ?? report.views[0];
  const defaults = useMemo(() => (view ? defaultInputs(report, view) : null), [report, view]);
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [method, setMethod] = useState<Method>("gordon");
  const [years, setYears] = useState<number | null>(null);
  const [growth, setGrowth] = useState<string | null>(null);
  const [multiple, setMultiple] = useState<string | null>(null);
  const [period, setPeriod] = useState<"quarter" | "year">("year");
  const id = useId();

  if (!view || !defaults) return null;

  const textOf = (spec: FieldSpec) => texts[spec.key] ?? toText(defaults[spec.key], spec.unit);
  const inputs: Inputs = { ...defaults, method };
  for (const group of GROUPS) {
    for (const spec of group.fields) {
      const text = textOf(spec);
      if (spec.key === "ebitTax") {
        inputs.ebitTax = text.trim() === "" ? null : fromText(text, spec.unit);
      } else if (spec.key === "dilutedShares") {
        inputs.dilutedShares = text.trim() === "" ? null : fromText(text, spec.unit);
      } else {
        inputs[spec.key] = fromText(text, spec.unit);
      }
    }
  }
  inputs.horizonYears = years ?? defaults.horizonYears;
  inputs.growth = growth === null ? defaults.growth : fromText(growth, "percent");
  inputs.multiple = multiple === null ? defaults.multiple : Number(multiple);

  const result = valuate(view, inputs);
  const waccSteps = report.inputs.wacc_steps.map(Number);
  const growthSteps = report.inputs.growth_steps.map(Number);
  const cells = result.ok ? matrix(view, inputs, waccSteps, growthSteps) : [];
  const title = `${report.company_name}, ${view.label}`;
  const reset = () => {
    setTexts({});
    setYears(null);
    setGrowth(null);
    setMultiple(null);
    setMethod("gordon");
  };

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <form className="flex flex-col gap-6" onSubmit={(event) => event.preventDefault()}>
        <SelectField
          id={`${id}-view`}
          label="Scenario"
          value={String(viewIndex)}
          onChange={(event) => setViewIndex(Number(event.target.value))}
        >
          {report.views.map((item, index) => (
            <option key={item.scenario} value={index}>
              {item.label}
            </option>
          ))}
        </SelectField>
        <SelectField
          id={`${id}-horizon`}
          label="Forecast horizon, years"
          value={String(inputs.horizonYears)}
          onChange={(event) => setYears(Number(event.target.value))}
        >
          {[1, 2, 3, 4, 5].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </SelectField>
        <fieldset className="flex flex-col gap-3">
          <legend className="font-medium text-ink">Terminal value</legend>
          <SelectField
            id={`${id}-method`}
            label="Method"
            value={method}
            onChange={(event) => setMethod(event.target.value as Method)}
          >
            <option value="gordon">Perpetual growth</option>
            <option value="exit_multiple">Exit multiple</option>
          </SelectField>
          {method === "gordon" ? (
            <TextField
              id={`${id}-growth`}
              label="Terminal growth, %"
              type="number"
              step="any"
              value={growth ?? toText(defaults.growth, "percent")}
              onChange={(event) => setGrowth(event.target.value)}
            />
          ) : (
            <TextField
              id={`${id}-multiple`}
              label="Exit multiple, EV / EBITDA"
              hint="Assumed: this project holds no market data."
              type="number"
              step="any"
              value={multiple ?? String(defaults.multiple)}
              onChange={(event) => setMultiple(event.target.value)}
            />
          )}
        </fieldset>
        {GROUPS.map((group) => (
          <fieldset key={group.title} className="flex flex-col gap-3">
            <legend className="font-medium text-ink">{group.title}</legend>
            {group.fields.map((spec) => (
              <TextField
                key={spec.key}
                id={`${id}-${spec.key}`}
                label={spec.label}
                hint={spec.hint}
                type="number"
                step="any"
                value={textOf(spec)}
                onChange={(event) =>
                  setTexts((current) => ({ ...current, [spec.key]: event.target.value }))
                }
              />
            ))}
          </fieldset>
        ))}
        <Button type="button" variant="secondary" onClick={reset}>
          Back to the report values
        </Button>
      </form>

      <div className="flex min-w-0 flex-col gap-6">
        {!result.ok ? (
          <Alert tone="negative" title="This setting has no value" live>
            {result.message}
          </Alert>
        ) : (
          <>
            <div aria-live="polite" className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-panel border border-line bg-surface p-4">
                <p className="text-small text-ink-muted">Enterprise value (DCF, model)</p>
                <p className="font-display text-h3 text-ink tabular-nums">
                  {usd(result.chosen.enterprise)}
                </p>
              </div>
              <div className="rounded-panel border border-line bg-surface p-4">
                <p className="text-small text-ink-muted">Equity value (model)</p>
                <p className="font-display text-h3 text-ink tabular-nums">{usd(result.equity)}</p>
              </div>
            </div>
            {result.chosen.reason ? (
              <Alert tone="warning" title="Undefined">
                {result.chosen.reason}
              </Alert>
            ) : null}
            <p className="text-small text-ink-muted tabular-nums">
              Cost of equity {percent(result.costOfEquity, 2)}, WACC {percent(result.wacc, 2)}.
              Terminal value is {percent(result.chosen.share)} of EV.
              {result.retained !== null
                ? ` Today's holders keep ${percent(result.retained, 2)} of equity value.`
                : ""}
            </p>
            {result.sharesProblem ? (
              <Alert tone="negative" title="Ill-defined share count">
                {result.sharesProblem}
              </Alert>
            ) : null}
            {result.chosen.presentTerminal !== null ? (
              <CompositionBar
                explicit={result.presentExplicit}
                terminal={result.chosen.presentTerminal}
              />
            ) : null}
            {result.chosen.enterprise !== null && result.equity !== null ? (
              <figure>
                <figcaption className="mb-2 font-medium text-ink">
                  From enterprise value to equity value
                </figcaption>
                <BridgeFigure
                  steps={[
                    { label: "Enterprise value", value: result.chosen.enterprise, total: true },
                    { label: "Debt", value: -inputs.debt },
                    { label: "Cash", value: inputs.cash },
                    { label: "Other senior claims", value: -inputs.otherClaims },
                    { label: "Non-operating assets", value: inputs.nonOperating },
                    { label: "Equity value", value: result.equity, total: true },
                  ]}
                />
              </figure>
            ) : null}
            <div>
              <h3 className="mb-2 font-medium text-ink">Terminal methods compared</h3>
              <dl className="grid gap-3 text-small sm:grid-cols-2">
                <div>
                  <dt className="text-ink-muted">Perpetual growth</dt>
                  <dd className="text-ink tabular-nums">
                    EV {usd(result.gordon.enterprise)}, terminal {percent(result.gordon.share)},
                    implied multiple{" "}
                    {result.impliedMultiple === null
                      ? "undefined"
                      : `${result.impliedMultiple.toFixed(1)}x`}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">Exit multiple</dt>
                  <dd className="text-ink tabular-nums">
                    EV {usd(result.exit.enterprise)}, terminal {percent(result.exit.share)}, implied
                    growth {percent(result.impliedGrowth, 2)}
                  </dd>
                </div>
              </dl>
            </div>
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-medium text-ink">Discounted cash flow</h3>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setPeriod(period === "year" ? "quarter" : "year")}
                  >
                    {period === "year" ? "Show quarters" : "Show years"}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      downloadText(
                        "multiverse_dcf_MODEL.csv",
                        dcfCsv(title, result),
                        "text/csv;charset=utf-8",
                      )
                    }
                  >
                    Download DCF as CSV
                  </Button>
                </div>
              </div>
              {period === "year" ? (
                <DataTable
                  id="dcf-years"
                  caption="FCFF and present value by year, in USD"
                  columns={YEAR_COLUMNS}
                  rows={yearly(result.lines)}
                  rowKey={(row) => row.label}
                />
              ) : (
                <DataTable
                  id="dcf-quarters"
                  caption="FCFF and present value by quarter, in USD"
                  columns={QUARTER_COLUMNS}
                  rows={result.lines}
                  rowKey={(row) => row.label}
                />
              )}
            </div>
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-medium text-ink">Sensitivity of EV to WACC and growth</h3>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    downloadText(
                      "multiverse_sensitivity_MODEL.csv",
                      matrixCsv(title, cells),
                      "text/csv;charset=utf-8",
                    )
                  }
                >
                  Download matrix as CSV
                </Button>
              </div>
              <Matrix cells={cells} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
