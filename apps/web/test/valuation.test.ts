import { VALUATION_REPORT } from "@multiverse/contracts/valuation";
import { describe, expect, it } from "vitest";
import {
  dcfCsv,
  defaultInputs,
  discountFactor,
  gordonValue,
  impliedGrowth,
  matrix,
  matrixCsv,
  retainedShare,
  stressCsv,
  valuate,
  waccOf,
  weightedValue,
  yearly,
  type Inputs,
  type Valuation,
} from "@/valuation/dcf";

const report = VALUATION_REPORT;
const view = report.views[1];
if (!view) throw new Error("the report has no view with the decision");
const defaults = defaultInputs(report, view);

const value = (inputs: Inputs = defaults): Valuation => {
  const result = valuate(view, inputs);
  if (!result.ok) throw new Error(result.message);
  return result;
};

describe("the browser agrees with the finance engine", () => {
  const gordon = view.terminals.find((row) => row.method === "gordon");
  const exit = view.terminals.find((row) => row.method === "exit_multiple");

  it("on WACC", () => {
    expect(waccOf(defaults)).toBeCloseTo(report.wacc, 5);
  });

  it("on the present value of the forecast", () => {
    expect(value().presentExplicit).toBeCloseTo(Number(view.present_explicit), -1);
  });

  it("on EV by both methods", () => {
    expect(value().gordon.enterprise).toBeCloseTo(Number(gordon?.enterprise_value), -1);
    expect(value().exit.enterprise).toBeCloseTo(Number(exit?.enterprise_value), -1);
  });

  it("on equity value", () => {
    expect(value().equity).toBeCloseTo(Number(view.bridge.equity_value), -1);
  });

  it("on the implied growth and multiple", () => {
    expect(value().impliedGrowth).toBeCloseTo(exit?.implied_growth ?? 0, 4);
    expect(value().impliedMultiple).toBeCloseTo(gordon?.implied_multiple ?? 0, 2);
  });

  it("on every cell of the sensitivity matrix", () => {
    const steps = report.inputs.wacc_steps.map(Number);
    const growths = report.inputs.growth_steps.map(Number);
    const cells = matrix(view, defaults, steps, growths).flat();
    expect(cells).toHaveLength(view.sensitivity.length);
    cells.forEach((cell, index) => {
      const expected = view.sensitivity[index]?.enterprise_value;
      expect(cell.enterprise).toBeCloseTo(Number(expected), -1);
    });
  });
});

describe("known answers", () => {
  it("a flat perpetuity is worth flow over rate", () => {
    const terminal = gordonValue([0, 0, 0, 100], 0.1, 0);
    expect(terminal).toBeCloseTo(1000, 8);
  });

  it("a growing perpetuity is Gordon", () => {
    expect(gordonValue([0, 0, 0, 100], 0.1, 0.02)).toBeCloseTo(102 / 0.08, 8);
  });

  it("four quarters compound to one year, and a quarter is not rate / 4", () => {
    expect(discountFactor(4, 0.1)).toBeCloseTo(1 / 1.1, 12);
    expect(discountFactor(1, 0.1)).not.toBeCloseTo(1 / 1.025, 5);
  });

  it("implied growth undoes the perpetuity", () => {
    const flows = [10, 20, 30, 40];
    const terminal = gordonValue(flows, 0.09, 0.025) ?? 0;
    expect(impliedGrowth(terminal, flows, 0.09)).toBeCloseTo(0.025, 10);
  });
});

describe("refusals", () => {
  it("refuses WACC at or below growth, with the reason", () => {
    const result = valuate(view, { ...defaults, growth: 0.2 });
    expect(result.ok).toBe(false);
    expect(result).toMatchObject({ code: "wacc_not_above_growth" });
    expect(!result.ok && result.message).toContain("no finite value");
  });

  it("refuses an empty parameter", () => {
    expect(valuate(view, { ...defaults, beta: Number.NaN })).toMatchObject({ code: "not_finite" });
  });

  it("refuses an exit multiple at or below zero", () => {
    const result = valuate(view, { ...defaults, method: "exit_multiple", multiple: 0 });
    expect(result).toMatchObject({ code: "multiple_not_positive" });
  });

  it("refuses a weight outside a whole", () => {
    expect(weightedValue([1, 2, 3], [0.5, 0.5, 0.5])).toBeNull();
    expect(weightedValue([1, 2, 3], [-0.1, 0.6, 0.5])).toBeNull();
    expect(weightedValue([80, 100, 130], [0.25, 0.5, 0.25])).toBeCloseTo(102.5, 8);
  });

  it("treats an ill-defined share count as a problem, not a number", () => {
    expect(retainedShare(0, 10).problem).toBeTruthy();
    expect(retainedShare(100, -1).problem).toBeTruthy();
    expect(retainedShare(90, 10).share).toBeCloseTo(0.9, 10);
  });

  it("leaves a cell empty where WACC is at or below growth", () => {
    const cells = matrix(view, defaults, [0], [0.5]);
    expect(cells[0]?.[0]?.enterprise).toBeNull();
  });
});

describe("parameters", () => {
  it("a higher WACC lowers value and keeps debt out of EV", () => {
    const higher = value({ ...defaults, beta: 1.4 });
    expect(higher.chosen.enterprise ?? 0).toBeLessThan(value().chosen.enterprise ?? 0);
    const owing = value({ ...defaults, debt: defaults.debt + 1000 });
    expect(owing.chosen.enterprise).toBe(value().chosen.enterprise);
    expect(owing.equity).toBeCloseTo((value().equity ?? 0) - 1000, 3);
  });

  it("a shorter horizon uses fewer quarters and still gives a value", () => {
    const short = value({ ...defaults, horizonYears: 3 });
    expect(short.lines).toHaveLength(12);
    expect(short.chosen.enterprise).not.toBeNull();
  });

  it("scaling FCFF leaves the price of a deal alone", () => {
    const half = value({ ...defaults, fcffScale: 0.5 });
    const deal = view.rows.find((row) => Number(row.transactions) !== 0);
    const line = half.lines.find((item) => item.quarter === deal?.quarter);
    const operating = Number(deal?.fcff) - Number(deal?.transactions);
    expect(line?.fcff).toBeCloseTo(operating / 2 + Number(deal?.transactions), 2);
  });

  it("a higher tax on EBIT lowers value", () => {
    const taxed = value({ ...defaults, ebitTax: 0.35 });
    expect(taxed.chosen.enterprise ?? 0).toBeLessThan(value().chosen.enterprise ?? 0);
  });

  it("non-operating assets add to equity value only", () => {
    const more = value({ ...defaults, nonOperating: 500 });
    expect(more.equity).toBeCloseTo((value().equity ?? 0) + 500, 3);
  });
});

describe("tables and files", () => {
  it("years add up to the quarters", () => {
    const result = value();
    const total = yearly(result.lines).reduce((sum, year) => sum + year.present, 0);
    expect(total).toBeCloseTo(result.presentExplicit, 2);
    expect(yearly(result.lines)).toHaveLength(5);
  });

  it("every CSV opens by saying what the numbers are", () => {
    const result = value();
    const cells = matrix(view, defaults, [0], [0]);
    for (const file of [dcfCsv("Case", result), matrixCsv("Case", cells), stressCsv(report)]) {
      expect(file.split("\n")[0]).toContain("not a verified market value");
    }
  });

  it("the DCF file holds every quarter and both values", () => {
    const file = dcfCsv("Case", value());
    expect(file).toContain("enterprise_value");
    expect(file).toContain("equity_value");
    expect(file.split("\n").length).toBeGreaterThan(view.rows.length + 3);
  });
});

describe("the report", () => {
  it("keeps its label and passes its required checks", () => {
    expect(report.value_label).toBe("Model value, not a verified market value");
    expect(report.sensitivity_label).toBe("Predictive sensitivity, not causal");
    const required = report.checks.filter((check) => check.key.startsWith("must_"));
    expect(required.length).toBeGreaterThan(5);
    expect(required.every((check) => check.passed)).toBe(true);
  });

  it("orders the tornado widest first", () => {
    const spreads = report.tornado.map((row) => Number(row.high_value) - Number(row.low_value));
    expect(spreads).toEqual([...spreads].sort((a, b) => b - a));
  });
});
