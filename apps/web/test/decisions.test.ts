import { readFileSync } from "node:fs";
import type { ScenarioDraft } from "@multiverse/contracts";
import { DEMO_DOSSIERS } from "@multiverse/contracts/demo";
import type { DecisionType } from "@multiverse/contracts/interventions";
import { describe, expect, it } from "vitest";
import { DECISION_TYPES } from "@/decisions/catalog";
import { buildCompanyContext, type CompanyContext } from "@/decisions/context";
import {
  defaultScenarioForm,
  moveDefaultDates,
  readScenarioForm,
  type ScenarioForm,
  scenarioFormFromDraft,
  toScenarioDraft,
} from "@/decisions/form";
import { parseScenarioDraft } from "@/decisions/parse";
import { addQuarters, type Issue } from "@/decisions/rules";
import { fromInput, toInput } from "@/decisions/units";
import { freshness, validateScenario } from "@/decisions/validate";
import { add, compare, div, mul, parseUserDecimal, toDecimalString } from "@/lib/decimal";

interface FixtureCase {
  name: string;
  model: string;
  code?: string;
  path?: string;
  payload: unknown;
}

function fixtures(file: string): FixtureCase[] {
  const url = new URL(`../../../packages/contracts/fixtures/${file}`, import.meta.url);
  const cases = JSON.parse(readFileSync(url, "utf8")) as FixtureCase[];
  return cases.filter((item) => item.model === "ScenarioDraft");
}

const IDS = {
  northwind: "5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13",
  aurora: "c91f5b37-2d6e-4a08-93bc-71e4d0a8f562",
  tessaract: "0f6a2c8e-9b1d-4e53-a7c4-58d2e1b9f036",
  kestrel: "e4b8d0a2-7c3f-4196-b2e5-9a0c6d1f8e47",
  valtrix: "8d2c6e1a-4f9b-4b70-8e3d-c5a1f7b2e906",
} as const;

function context(id: string): CompanyContext {
  const dossier = DEMO_DOSSIERS.find((candidate) => candidate.company.company_id === id);
  if (!dossier) throw new Error(`no dossier ${id}`);
  return buildCompanyContext(dossier);
}

function form(id: string, type: DecisionType, asOf?: string): ScenarioForm {
  const ctx = context(id);
  return defaultScenarioForm(id, asOf ?? ctx.cutoffs[0]?.asOf ?? "2022-12-31", type, "synthetic");
}

function codes(issues: Issue[], severity: Issue["severity"] = "error"): string[] {
  return issues.filter((issue) => issue.severity === severity).map((issue) => issue.code);
}

function withDecision(base: ScenarioForm, change: Partial<ScenarioForm["decision"]>): ScenarioForm {
  return { ...base, decision: { ...base.decision, ...change } };
}

describe("exact decimals", () => {
  it("adds financing shares without floating-point error", () => {
    expect(toDecimalString(add(add("0.7", "0.2"), "0.1"))).toBe("1");
    expect(0.7 + 0.2 + 0.1).not.toBe(1);
  });

  it("multiplies, divides and rounds half away from zero", () => {
    expect(toDecimalString(mul("412500000", "0.4"))).toBe("165000000");
    expect(toDecimalString(div("1", "3", 4))).toBe("0.3333");
    expect(toDecimalString(div("-5", "2", 0))).toBe("-3");
    expect(compare("0.50", "0.5")).toBe(0);
  });

  it("reads typed numbers but refuses ambiguous ones", () => {
    expect(parseUserDecimal(" +40 ")).toBe("40");
    expect(parseUserDecimal("−12.50")).toBe("-12.5");
    expect(parseUserDecimal(".5")).toBe("0.5");
    expect(parseUserDecimal("1,5")).toBeNull();
    expect(parseUserDecimal("1e3")).toBeNull();
    expect(parseUserDecimal("abc")).toBeNull();
  });

  it("converts display units by exact powers of ten", () => {
    expect(fromInput("40", "fraction")).toBe("0.4");
    expect(fromInput("5.5", "fraction")).toBe("0.055");
    expect(toInput("1000000000", "usd")).toBe("1000");
    expect(fromInput("1.5", "usd")).toBe("1500000");
    expect(fromInput("2", "percentage_points")).toBe("2");
  });

  it("adds quarters like the Python contracts", () => {
    expect(addQuarters("2022-11-30", 1)).toBe("2023-02-28");
    expect(addQuarters("2023-11-30", 1)).toBe("2024-02-29");
    expect(addQuarters("2022-12-31", 20)).toBe("2027-12-31");
  });
});

describe("shared contract fixtures", () => {
  it.each(fixtures("valid.json").map((item) => [item.name, item] as const))(
    "accepts %s",
    (_name, item) => {
      const parsed = parseScenarioDraft(item.payload);
      expect(parsed.issues).toEqual([]);
      expect(parsed.draft).not.toBeNull();
    },
  );

  it.each(fixtures("invalid.json").map((item) => [item.name, item] as const))(
    "rejects %s with the same code as Python",
    (_name, item) => {
      const parsed = parseScenarioDraft(item.payload);
      expect(parsed.draft).toBeNull();
      expect(parsed.issues.map(({ code, path }) => ({ code, path }))).toEqual([
        { code: item.code, path: item.path },
      ]);
    },
  );

  it("covers every decision type", () => {
    const types = new Set(
      fixtures("valid.json").map((item) => (item.payload as ScenarioDraft).decision.type),
    );
    expect([...types].sort()).toEqual([...DECISION_TYPES].sort());
  });
});

describe("JSON round trip", () => {
  it.each(fixtures("valid.json").map((item) => [item.name, item] as const))(
    "rebuilds %s from its form",
    (_name, item) => {
      const draft = item.payload as ScenarioDraft;
      const rebuilt = scenarioFormFromDraft(draft);
      const read = readScenarioForm(rebuilt);
      const again = toScenarioDraft(rebuilt, read);
      expect(read.issues).toEqual([]);
      expect(again).toEqual(draft);
      expect(JSON.parse(JSON.stringify(again))).toEqual(draft);
    },
  );
});

describe("documented defaults", () => {
  it.each(DECISION_TYPES.filter((type) => type !== "rnd_change"))(
    "form a valid %s decision for Northwind",
    (type) => {
      const result = validateScenario(form(IDS.northwind, type), context(IDS.northwind));
      expect(codes(result.issues)).toEqual([]);
      expect(result.draft?.decision.type).toBe(type);
    },
  );

  it("leave the R&D unit unchosen, so its meaning must be picked (US-03)", () => {
    const base = form(IDS.northwind, "rnd_change");
    const result = validateScenario(
      withDecision(base, { magnitude: { value: "40", unit: "" } }),
      context(IDS.northwind),
    );
    expect(codes(result.issues)).toEqual(["unit_required"]);
    expect(result.issues[0]?.path).toBe("decision.magnitude.unit");
  });

  it("move the untouched dates along with the cutoff", () => {
    const decision = form(IDS.northwind, "capex_expansion", "2022-12-31").decision;
    const moved = moveDefaultDates(decision, "2022-12-31", "2022-06-30");
    expect(moved.timing.announcement_date).toBe("2022-06-30");
    expect(moved.timing.effective_date).toBe("2022-07-01");
    const edited = { ...decision, timing: { ...decision.timing, effective_date: "2023-06-01" } };
    expect(moveDefaultDates(edited, "2022-12-31", "2022-06-30")).toBe(edited);
  });
});

describe("validation of a Northwind decision", () => {
  const ctx = context(IDS.northwind);
  const asOf = ctx.cutoffs[0]?.asOf ?? "";
  const rnd = (value: string, unit: "fraction_of_previous_rnd_budget" | "pp_of_revenue" | "") =>
    withDecision(form(IDS.northwind, "rnd_change", asOf), { magnitude: { value, unit } });

  it("translates +40% of the R&D budget into dollars and into percentage points", () => {
    const result = validateScenario(rnd("40", "fraction_of_previous_rnd_budget"), ctx);
    const budget = ctx.cutoffs[0]?.rnd.value ?? "0";
    expect(result.errors).toBe(0);
    const labels = result.resolved.map((line) => line.label);
    expect(labels).toContain("Change in yearly R&D spending");
    expect(labels).toContain("Same change in percentage points of revenue");
    expect(result.draft?.decision.magnitude).toEqual({
      value: "0.4",
      unit: "fraction_of_previous_rnd_budget",
    });
    expect(compare(mul(budget, "0.4"), "0")).toBe(1);
  });

  it("rejects a value above the hard limit and flags one outside the planning range", () => {
    expect(
      codes(validateScenario(rnd("600", "fraction_of_previous_rnd_budget"), ctx).issues),
    ).toEqual(["out_of_range"]);
    const ood = validateScenario(rnd("300", "fraction_of_previous_rnd_budget"), ctx);
    expect(ood.errors).toBe(0);
    expect(codes(ood.issues, "warning")).toContain("out_of_distribution");
  });

  it("reports text that is not a number at the field", () => {
    const result = validateScenario(rnd("forty", "pp_of_revenue"), ctx);
    expect(result.issues).toEqual([
      expect.objectContaining({ code: "not_a_number", path: "decision.magnitude.value" }),
    ]);
  });

  it("requires financing shares of exactly 100% and never normalizes them (US-04)", () => {
    const base = form(IDS.northwind, "acquisition", asOf);
    const short = validateScenario(
      withDecision(base, { shares: { cash: "60", debt: "30", equity: "5" } }),
      ctx,
    );
    expect(codes(short.issues)).toEqual(["shares_sum"]);
    expect(short.issues[0]?.message).toContain("add up to 95%");
    expect(short.draft).toBeNull();

    const exact = validateScenario(
      withDecision(base, { shares: { cash: "60", debt: "40", equity: "0" } }),
      ctx,
    );
    expect(exact.errors).toBe(0);
    expect(exact.draft?.decision).toMatchObject({
      financing: { cash: "0.6", debt: "0.4", equity: "0" },
    });
  });

  it("warns that new equity dilutes without modelling it", () => {
    const base = form(IDS.northwind, "acquisition", asOf);
    const result = validateScenario(
      withDecision(base, { shares: { cash: "50", debt: "30", equity: "20" } }),
      ctx,
    );
    expect(codes(result.issues, "warning")).toContain("dilution_not_modelled");
  });

  it("rejects an effective date before the announcement", () => {
    const base = form(IDS.northwind, "debt_refinance", asOf);
    const result = validateScenario(
      withDecision(base, {
        timing: {
          ...base.decision.timing,
          announcement_date: "2023-03-01",
          effective_date: "2023-02-01",
        },
      }),
      ctx,
    );
    expect(codes(result.issues)).toEqual(["effective_before_announcement"]);
  });

  it("asks for whole quarters", () => {
    const base = form(IDS.northwind, "capex_expansion", asOf);
    const result = validateScenario(
      withDecision(base, { timing: { ...base.decision.timing, lag_quarters: "2.5" } }),
      ctx,
    );
    expect(codes(result.issues)).toEqual(["not_integer"]);
  });
});

describe("eligibility", () => {
  it("blocks an unsupported company (FC-01)", () => {
    const ctx = context(IDS.valtrix);
    const result = validateScenario(
      defaultScenarioForm(IDS.valtrix, "2022-12-31", "capex_expansion", "synthetic"),
      ctx,
    );
    expect(codes(result.issues)).toContain("company_unsupported");
  });

  it("blocks a decision that takes effect after the company left the market", () => {
    const ctx = context(IDS.aurora);
    const base = form(IDS.aurora, "capex_expansion");
    const later = withDecision(base, {
      timing: { ...base.decision.timing, effective_date: "2021-10-01" },
    });
    expect(codes(validateScenario(later, ctx).issues)).toContain("company_left_market");
    expect(codes(validateScenario(base, ctx).issues, "warning")).toContain("horizon_after_exit");
  });

  it("warns about insufficient history but allows a demo (FC-02)", () => {
    const result = validateScenario(form(IDS.tessaract, "capex_expansion"), context(IDS.tessaract));
    expect(result.errors).toBe(0);
    expect(codes(result.issues, "warning")).toContain("insufficient_history");
  });

  it("needs the base figure of a relative unit at the cutoff", () => {
    const ctx = context(IDS.kestrel);
    const cutoff = ctx.cutoffs.find(
      (facts) => facts.quartersPublic > 0 && facts.revenue.value === null,
    );
    expect(cutoff, "a Kestrel cutoff whose revenue window includes CAD quarters").toBeDefined();
    const base = form(IDS.kestrel, "divestiture", cutoff?.asOf);
    expect(codes(validateScenario(base, ctx).issues)).toContain("base_unavailable");
  });

  it("warns when a company reports no R&D", () => {
    const ctx = context(IDS.aurora);
    const base = withDecision(form(IDS.aurora, "rnd_change"), {
      magnitude: { value: "1", unit: "pp_of_revenue" },
    });
    expect(codes(validateScenario(base, ctx).issues, "warning")).toContain("no_rnd_history");
    const relative = withDecision(base, {
      magnitude: { value: "20", unit: "fraction_of_previous_rnd_budget" },
    });
    expect(codes(validateScenario(relative, ctx).issues)).toContain("base_unavailable");
  });
});

describe("stale results (FR-TM-03)", () => {
  const ctx = context(IDS.northwind);
  const base = form(IDS.northwind, "capex_expansion");
  const result = validateScenario(base, ctx);

  it("are fresh until something changes", () => {
    expect(freshness(result, base)).toEqual({ state: "fresh" });
  });

  it("are stale when the cutoff changes, even if nothing else did", () => {
    const other = ctx.cutoffs[1]?.asOf ?? "";
    expect(freshness(result, { ...base, as_of: other })).toEqual({
      state: "stale_as_of",
      from: base.as_of,
      to: other,
    });
  });

  it("are out of date when an input changes", () => {
    const changed = withDecision(base, { magnitude: { value: "600", unit: "usd" } });
    expect(freshness(result, changed)).toEqual({ state: "changed" });
  });

  it("resolve to different dollars at a different cutoff", () => {
    const earlier =
      ctx.cutoffs.find((facts) => facts.asOf < base.as_of && facts.rnd.value !== null)?.asOf ?? "";
    const rndForm = (asOf: string) =>
      withDecision(form(IDS.northwind, "rnd_change", asOf), {
        magnitude: { value: "40", unit: "fraction_of_previous_rnd_budget" },
      });
    const now = validateScenario(rndForm(base.as_of), ctx).resolved[1]?.value;
    const then = validateScenario(rndForm(earlier), ctx).resolved[1]?.value;
    expect(now).toBeDefined();
    expect(then).toBeDefined();
    expect(now).not.toBe(then);
  });
});

describe("company facts at a cutoff", () => {
  it("only sum quarters that were public by the cutoff", () => {
    const ctx = context(IDS.northwind);
    const facts = ctx.cutoffs[0];
    expect(facts?.revenue.quarters).toHaveLength(4);
    // The quarter that ends on the cutoff was filed later, so it is not in the window.
    expect(facts?.revenue.quarters[0]).not.toBe("FY2022 Q4");
    expect(facts && compare(facts.revenue.value ?? "0", div("0", "1"))).toBe(1);
  });
});
