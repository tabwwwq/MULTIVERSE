import { SIMULATION_REPORT } from "@multiverse/contracts/simulation";
import { describe, expect, it } from "vitest";
import {
  convergenceSizes,
  driverText,
  originCounts,
  percent,
  probabilityText,
  settledShare,
} from "@/simulation/report";

const report = SIMULATION_REPORT;

describe("the stored run", () => {
  it("says it is conditional and not validated", () => {
    expect(report.validation).toBe("conditional_non_validated");
    expect(report.probability_label).toBe("Conditional on the assumed model, not validated");
    expect(report.result.calibrated).toBe(false);
    expect(report.result.mock).toBe(false);
    expect(report.result.uncertainty_type).toBe("conditional_model_quantiles");
  });

  it("names the data, the model and the versions behind it", () => {
    expect(report.manifest.dataset_id).toMatch(/^fds-/);
    expect(report.manifest.model_id).toMatch(/^model-/);
    expect(report.manifest.finance_version).toBeTruthy();
    expect(report.manifest.shock_model).toContain("block bootstrap");
  });

  it("keeps assumptions apart from what was observed", () => {
    const counts = originCounts(report);
    expect(counts.observed).toBeGreaterThan(0);
    expect(counts.assumed).toBeGreaterThan(0);
    expect(counts.implied).toBeGreaterThan(0);
  });

  it("converges through the sizes the protocol asks for", () => {
    expect(convergenceSizes(report)).toEqual([500, 1000, 3000, 10000]);
    expect(settledShare(report, 10000)).toBe(1);
  });
});

describe("probabilityText", () => {
  const risk = report.risks.find((row) => row.risk === "covenant_breach") ?? report.risks[0];
  if (!risk) throw new Error("the run has no risks");

  it("never shows zero as if it were no risk", () => {
    const text = probabilityText({ ...risk, probability: 0, standard_error: 0, upper_95: 0.0004 });
    expect(text).toBe("None seen, below 0.04%");
  });

  it("shows a share with two Monte Carlo errors", () => {
    const text = probabilityText({ ...risk, probability: 0.181, standard_error: 0.004 });
    expect(text).toBe("18.1% ± 0.8%");
  });
});

describe("driverText", () => {
  const driver = report.tails[0]?.drivers[0];
  if (!driver) throw new Error("the run has no tails");

  it("signs points and answers yes or no", () => {
    expect(driverText({ ...driver, value: 1.5, unit: "points_of_growth" })).toBe("+1.50 points");
    expect(driverText({ ...driver, value: -2, unit: "points_of_rate" })).toBe("-2.00 points");
    expect(driverText({ ...driver, value: 0, unit: "yes_no" })).toBe("No");
  });
});

describe("percent", () => {
  it("rounds to the digits asked", () => {
    expect(percent(0.1234)).toBe("12.3%");
    expect(percent(0.5, 0)).toBe("50%");
  });
});
