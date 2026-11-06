import type { ValuationReport } from "@multiverse/contracts";

/*
 * The DCF of the finance engine, again in the browser, so parameters can be edited without a
 * server. It reads the statements the engine reconciled and only redoes the discounting. A test
 * holds it to the numbers of the Python report.
 */

export type View = ValuationReport["views"][number];
type Row = View["rows"][number];
export type Method = "gordon" | "exit_multiple";

const QUARTERS = 4;

export interface Inputs {
  riskFree: number;
  equityRiskPremium: number;
  beta: number;
  costOfDebt: number;
  capitalTax: number;
  debtWeight: number;
  /** Tax on EBIT. Null keeps the tax of the statements, with their carried losses. */
  ebitTax: number | null;
  horizonYears: number;
  /** Scale of operating FCFF: 1 is the projection as it stands. */
  fcffScale: number;
  method: Method;
  growth: number;
  multiple: number;
  debt: number;
  cash: number;
  otherClaims: number;
  nonOperating: number;
  dilutedShares: number | null;
  newShares: number;
}

export interface Line {
  quarter: number;
  label: string;
  fcff: number;
  recurring: number;
  ebitda: number;
  factor: number;
  present: number;
}

export interface TerminalResult {
  terminalValue: number | null;
  presentTerminal: number | null;
  enterprise: number | null;
  share: number | null;
  reason: string | null;
}

export interface Valuation {
  ok: true;
  costOfEquity: number;
  wacc: number;
  lines: Line[];
  presentExplicit: number;
  gordon: TerminalResult;
  exit: TerminalResult;
  chosen: TerminalResult;
  impliedGrowth: number | null;
  impliedMultiple: number | null;
  equity: number | null;
  retained: number | null;
  sharesProblem: string | null;
}

export interface Refusal {
  ok: false;
  code: string;
  message: string;
}

export function defaultInputs(report: ValuationReport, view: View): Inputs {
  const { capital, inputs } = report;
  return {
    riskFree: Number(capital.risk_free),
    equityRiskPremium: Number(capital.equity_risk_premium),
    beta: Number(capital.beta),
    costOfDebt: Number(capital.pre_tax_cost_of_debt),
    capitalTax: Number(capital.tax_rate),
    debtWeight: Number(capital.debt_weight),
    ebitTax: null,
    horizonYears: view.rows.length / QUARTERS,
    fcffScale: 1,
    method: "gordon",
    growth: Number(capital.terminal_growth),
    multiple: Number(inputs.exit_multiple),
    debt: Number(view.bridge.debt),
    cash: Number(view.bridge.cash),
    otherClaims: Number(view.bridge.other_senior_claims),
    nonOperating: Number(view.bridge.non_operating_assets),
    dilutedShares: inputs.diluted_shares ? Number(inputs.diluted_shares) : null,
    newShares: 0,
  };
}

export function costOfEquity(inputs: Inputs): number {
  return inputs.riskFree + inputs.beta * inputs.equityRiskPremium;
}

export function waccOf(inputs: Inputs): number {
  const debt = inputs.costOfDebt * (1 - inputs.capitalTax);
  return (1 - inputs.debtWeight) * costOfEquity(inputs) + inputs.debtWeight * debt;
}

/** End of a quarter, from an effective annual rate: not rate / 4. */
export function discountFactor(quarter: number, rate: number): number {
  return (1 + rate) ** (-quarter / QUARTERS);
}

function adjust(row: Row, inputs: Inputs): { fcff: number; recurring: number } {
  const tax = Number(row.tax_on_ebit);
  const changed = inputs.ebitTax === null ? tax : Math.max(Number(row.ebit), 0) * inputs.ebitTax;
  const transactions = Number(row.transactions);
  const operating = Number(row.fcff) - transactions + tax - changed;
  return {
    fcff: operating * inputs.fcffScale + transactions,
    recurring: (Number(row.fcff_recurring) + tax - changed) * inputs.fcffScale,
  };
}

function refuse(inputs: Inputs, wacc: number): Refusal | null {
  const numbers = Object.values(inputs).filter((value) => typeof value === "number");
  if (numbers.some((value) => !Number.isFinite(value))) {
    return { ok: false, code: "not_finite", message: "Every parameter needs a number." };
  }
  if (inputs.debtWeight < 0 || inputs.debtWeight > 1) {
    return { ok: false, code: "out_of_range", message: "The debt weight lies between 0 and 100%." };
  }
  if (inputs.capitalTax < 0 || inputs.capitalTax > 1) {
    return { ok: false, code: "out_of_range", message: "A tax rate lies between 0 and 100%." };
  }
  if (inputs.ebitTax !== null && (inputs.ebitTax < 0 || inputs.ebitTax > 1)) {
    return { ok: false, code: "out_of_range", message: "A tax rate lies between 0 and 100%." };
  }
  if (wacc <= 0) {
    return { ok: false, code: "rate_not_positive", message: "WACC must be above 0." };
  }
  if (inputs.method === "gordon" && wacc <= inputs.growth) {
    return {
      ok: false,
      code: "wacc_not_above_growth",
      message: `WACC ${(wacc * 100).toFixed(2)}% is not above terminal growth ${(inputs.growth * 100).toFixed(2)}%. A perpetuity at this growth has no finite value.`,
    };
  }
  if (inputs.method === "exit_multiple" && inputs.multiple <= 0) {
    return {
      ok: false,
      code: "multiple_not_positive",
      message: "The exit multiple must be above 0.",
    };
  }
  return null;
}

function terminalOf(
  terminalValue: number | null,
  presentExplicit: number,
  factor: number,
  reason: string | null,
): TerminalResult {
  if (terminalValue === null) {
    return { terminalValue, presentTerminal: null, enterprise: null, share: null, reason };
  }
  const presentTerminal = terminalValue * factor;
  const enterprise = presentExplicit + presentTerminal;
  return {
    terminalValue,
    presentTerminal,
    enterprise,
    share: enterprise > 0 ? presentTerminal / enterprise : null,
    reason: enterprise > 0 ? null : "Enterprise value is not positive: its shares have no meaning.",
  };
}

/** TV = (1 + g)(1 + r) / (r − g) × Σ q_k / (1 + r)^(k/4): the form the Python engine uses. */
export function gordonValue(lastYear: readonly number[], rate: number, growth: number) {
  if (rate <= growth) return null;
  const sum = lastYear.reduce((total, flow) => total + flow, 0);
  if (sum <= 0) return null;
  const year = lastYear.reduce((total, flow, k) => total + flow * discountFactor(k + 1, rate), 0);
  return (((1 + growth) * (1 + rate)) / (rate - growth)) * year;
}

export function impliedGrowth(
  terminalValue: number,
  lastYear: readonly number[],
  rate: number,
): number | null {
  const year = lastYear.reduce((total, flow, k) => total + flow * discountFactor(k + 1, rate), 0);
  if (year <= 0 || terminalValue <= 0) return null;
  const grown = (1 + rate) * year;
  return (terminalValue * rate - grown) / (terminalValue + grown);
}

/** A share of equity left to today's holders. Never a price: D-06 keeps that out of V1 to V3. */
export function retainedShare(diluted: number | null, added: number) {
  if (diluted === null) return { share: null, problem: null };
  if (!Number.isFinite(diluted) || diluted <= 0) {
    return { share: null, problem: "Diluted shares must be above 0." };
  }
  if (!Number.isFinite(added) || added < 0) {
    return { share: null, problem: "New shares cannot be negative." };
  }
  return { share: diluted / (diluted + added), problem: null };
}

export function valuate(view: View, inputs: Inputs): Valuation | Refusal {
  const wacc = waccOf(inputs);
  const refused = refuse(inputs, wacc);
  if (refused) return refused;

  const rows = view.rows.slice(0, inputs.horizonYears * QUARTERS);
  const lines = rows.map((row): Line => {
    const { fcff, recurring } = adjust(row, inputs);
    const factor = discountFactor(row.quarter, wacc);
    return {
      quarter: row.quarter,
      label: row.label,
      fcff,
      recurring,
      ebitda: Number(row.adjusted_ebitda),
      factor,
      present: fcff * factor,
    };
  });
  const presentExplicit = lines.reduce((total, line) => total + line.present, 0);
  const lastYear = lines.slice(-QUARTERS);
  const flows = lastYear.map((line) => line.recurring);
  const ebitda = lastYear.reduce((total, line) => total + line.ebitda, 0);
  const factor = discountFactor(lines.length, wacc);

  const gordonTv = gordonValue(flows, wacc, inputs.growth);
  const gordon = terminalOf(
    gordonTv,
    presentExplicit,
    factor,
    gordonTv === null
      ? "Undefined: recurring FCFF of the last year is not positive, or WACC ≤ g."
      : null,
  );
  const exitTv = ebitda > 0 && inputs.multiple > 0 ? ebitda * inputs.multiple : null;
  const exit = terminalOf(
    exitTv,
    presentExplicit,
    factor,
    exitTv === null ? "Undefined: EBITDA of the last year is not positive." : null,
  );
  const chosen = inputs.method === "gordon" ? gordon : exit;
  const equity =
    chosen.enterprise === null
      ? null
      : chosen.enterprise - inputs.debt + inputs.cash - inputs.otherClaims + inputs.nonOperating;
  const shares = retainedShare(inputs.dilutedShares, inputs.newShares);
  return {
    ok: true,
    costOfEquity: costOfEquity(inputs),
    wacc,
    lines,
    presentExplicit,
    gordon,
    exit,
    chosen,
    impliedGrowth: exitTv === null ? null : impliedGrowth(exitTv, flows, wacc),
    impliedMultiple: gordonTv === null || ebitda <= 0 ? null : gordonTv / ebitda,
    equity,
    retained: shares.share,
    sharesProblem: shares.problem,
  };
}

export interface Cell {
  wacc: number;
  growth: number;
  enterprise: number | null;
}

/** WACC by growth. Where WACC is at or below growth no value exists, and the cell is empty. */
export function matrix(
  view: View,
  inputs: Inputs,
  waccSteps: readonly number[],
  growthSteps: readonly number[],
): Cell[][] {
  const base = waccOf(inputs);
  const result = valuate(view, { ...inputs, method: "exit_multiple", multiple: 1 });
  const lines = result.ok ? result.lines : [];
  const lastYear = lines.slice(-QUARTERS).map((line) => line.recurring);
  return waccSteps.map((step) => {
    const wacc = base + step;
    const present = lines.reduce(
      (total, line) => total + line.fcff * discountFactor(line.quarter, wacc),
      0,
    );
    const factor = discountFactor(lines.length, wacc);
    return growthSteps.map((growthStep) => {
      const growth = inputs.growth + growthStep;
      const terminal = gordonValue(lastYear, wacc, growth);
      return {
        wacc,
        growth,
        enterprise: terminal === null ? null : present + terminal * factor,
      };
    });
  });
}

export function yearly(lines: readonly Line[]) {
  const years: { label: string; fcff: number; present: number }[] = [];
  for (let start = 0; start < lines.length; start += QUARTERS) {
    const part = lines.slice(start, start + QUARTERS);
    years.push({
      label: `${part[0]?.label ?? ""} to ${part.at(-1)?.label ?? ""}`,
      fcff: part.reduce((total, line) => total + line.fcff, 0),
      present: part.reduce((total, line) => total + line.present, 0),
    });
  }
  return years;
}

/** Scenario weights are shares of a whole. */
export function weightedValue(
  values: readonly number[],
  weights: readonly number[],
): number | null {
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  if (weights.some((weight) => !Number.isFinite(weight) || weight < 0)) return null;
  if (Math.abs(total - 1) > 1e-9 || values.length !== weights.length) return null;
  return values.reduce((sum, value, index) => sum + value * (weights[index] ?? 0), 0);
}

function cell(value: string | number): string {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const NOTICE = "# Model value, not a verified market value. Not advice. USD.";

export function dcfCsv(title: string, result: Valuation): string {
  const lines = [
    NOTICE,
    `# ${title}. WACC ${result.wacc.toFixed(6)}.`,
    "quarter,label,fcff,discount_factor,present_value",
    ...result.lines.map((line) =>
      [
        line.quarter,
        line.label,
        line.fcff.toFixed(2),
        line.factor.toFixed(8),
        line.present.toFixed(2),
      ]
        .map(cell)
        .join(","),
    ),
    `explicit,,,,${result.presentExplicit.toFixed(2)}`,
    `terminal,,${result.chosen.terminalValue?.toFixed(2) ?? "undefined"},,${result.chosen.presentTerminal?.toFixed(2) ?? "undefined"}`,
    `enterprise_value,,,,${result.chosen.enterprise?.toFixed(2) ?? "undefined"}`,
    `equity_value,,,,${result.equity?.toFixed(2) ?? "undefined"}`,
  ];
  return `${lines.join("\n")}\n`;
}

export function matrixCsv(title: string, cells: readonly Cell[][]): string {
  const growths = (cells[0] ?? []).map((item) => item.growth.toFixed(4));
  const lines = [
    NOTICE,
    `# ${title}. Rows: WACC. Columns: terminal growth.`,
    ["wacc", ...growths].join(","),
  ];
  for (const row of cells) {
    lines.push(
      [
        row[0]?.wacc.toFixed(4) ?? "",
        ...row.map((item) => item.enterprise?.toFixed(2) ?? "undefined"),
      ].join(","),
    );
  }
  return `${lines.join("\n")}\n`;
}

export function stressCsv(report: ValuationReport): string {
  const lines = [
    NOTICE,
    `# ${report.company_name}. Hypothetical decision. Central path, no shocks.`,
    "stress,enterprise_value,ev_change,lowest_cash,peak_leverage,lowest_interest_cover,first_breach,peak_shortfall",
  ];
  for (const row of report.stress) {
    lines.push(
      [
        row.label,
        row.enterprise_value ?? "undefined",
        row.ev_change ?? "undefined",
        row.lowest_cash,
        row.peak_leverage ?? "undefined",
        row.lowest_interest_cover ?? "undefined",
        row.first_breach ?? "none",
        row.peak_shortfall,
      ]
        .map(cell)
        .join(","),
    );
  }
  return `${lines.join("\n")}\n`;
}
