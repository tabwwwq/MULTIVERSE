import type { ScenarioDraft } from "@multiverse/contracts";
import type { Distribution } from "@multiverse/contracts/interventions";
import { formatMagnitude, specFor, unitSpecFor } from "@/decisions/catalog";
import type { BaseFigure, CutoffFacts } from "@/decisions/context";
import { centralValue } from "@/decisions/rules";
import { formatUsd, formatValue } from "@/decisions/units";
import {
  abs,
  add,
  compare,
  type Dec,
  div,
  isZero,
  mul,
  shift,
  sub,
  toDecimalString,
} from "@/lib/decimal";

/*
 * What a valid decision means in dollars at its knowledge cutoff. This is arithmetic on
 * the point-in-time figures, not a forecast: no model is involved. Uncertain parameters
 * use their central value (fixed value, midpoint or mode) and say so.
 */

export interface ResolvedLine {
  label: string;
  value: string;
  /** Where the number comes from. */
  basis: string;
}

type Decision = ScenarioDraft["decision"];

function usd(value: Dec | string, signed = false): string {
  return formatUsd(toDecimalString(div(value, "1", 0)), signed);
}

function basisOf(figure: BaseFigure, label: string): string {
  const quarters =
    figure.quarters.length === 4 ? "trailing four quarters" : figure.quarters.join(", ");
  return `${label}: ${formatUsd(figure.value ?? "0")}, ${quarters}${figure.lastFiled ? `, last filed ${figure.lastFiled}` : ""}`;
}

function central(decision: Decision, key: string): string {
  return centralValue((decision as unknown as Record<string, Distribution>)[key] as Distribution);
}

function funding(
  total: Dec,
  shares: { cash: string; debt: string; equity: string },
): ResolvedLine[] {
  const parts: [string, string][] = [
    ["Cash on hand", shares.cash],
    ["New debt", shares.debt],
    ["New equity", shares.equity],
  ];
  return parts
    .filter(([, share]) => !isZero(share))
    .map(([label, share]) => ({
      label: `Funded by ${label.toLowerCase()}`,
      value: usd(mul(total, share)),
      basis: `${formatValue(share, "fraction")} of ${usd(total)}`,
    }));
}

function rnd(
  decision: Extract<Decision, { type: "rnd_change" }>,
  facts: CutoffFacts,
): ResolvedLine[] {
  const { value, unit } = decision.magnitude;
  const budget = facts.rnd.value;
  const revenue = facts.revenue.value;
  const yearly =
    unit === "fraction_of_previous_rnd_budget"
      ? budget === null
        ? null
        : mul(budget, value)
      : revenue === null
        ? null
        : mul(revenue, shift(value, -2));
  if (yearly === null) return [];
  const lines: ResolvedLine[] = [
    {
      label: "Change in yearly R&D spending",
      value: usd(yearly, true),
      basis:
        unit === "fraction_of_previous_rnd_budget"
          ? basisOf(facts.rnd, "Previous R&D budget")
          : basisOf(facts.revenue, "Revenue"),
    },
  ];
  // The same decision in the other unit: the clearest proof that the two are different.
  if (unit === "fraction_of_previous_rnd_budget" && revenue !== null && !isZero(revenue)) {
    lines.push({
      label: "Same change in percentage points of revenue",
      value: formatValue(
        toDecimalString(div(shift(yearly, 2), revenue, 2)),
        "percentage_points",
        true,
      ),
      basis: basisOf(facts.revenue, "Revenue"),
    });
  }
  if (unit === "pp_of_revenue" && budget !== null && !isZero(budget)) {
    lines.push({
      label: "Same change as a share of the previous R&D budget",
      value: formatValue(toDecimalString(div(yearly, budget, 4)), "fraction", true),
      basis: basisOf(facts.rnd, "Previous R&D budget"),
    });
  }
  const capitalized = decision.capitalized_fraction;
  if (!isZero(capitalized)) {
    lines.push({
      label: "Capitalized instead of expensed",
      value: usd(mul(yearly, capitalized), true),
      basis: `${formatValue(capitalized, "fraction")} of the change`,
    });
  }
  // A cut frees cash; only an increase needs funding.
  const increase = compare(yearly, "0") > 0;
  return [...lines, ...(increase ? funding(yearly, decision.financing) : [])];
}

function workforce(
  decision: Extract<Decision, { type: "workforce_restructure" }>,
  facts: CutoffFacts,
): ResolvedLine[] {
  const revenue = facts.revenue.value;
  if (revenue === null) return [];
  const payroll = mul(revenue, decision.payroll_to_revenue);
  const gross = mul(payroll, decision.magnitude.value);
  const realized = mul(gross, central(decision, "savings_realization"));
  const months = central(decision, "one_off_cost_months");
  const oneOff = div(mul(abs(gross), months), "12", 0);
  return [
    {
      label: "Estimated yearly payroll",
      value: usd(payroll),
      basis: `${formatValue(decision.payroll_to_revenue, "fraction")} of revenue (assumption). ${basisOf(facts.revenue, "Revenue")}`,
    },
    {
      label: "Gross change in yearly payroll",
      value: usd(gross, true),
      basis: `${formatValue(decision.magnitude.value, "fraction", true)} of headcount`,
    },
    {
      label: "Change that shows up in costs",
      value: usd(realized, true),
      basis: `Central value: ${formatValue(central(decision, "savings_realization"), "fraction")} realized`,
    },
    {
      label: "One-off cost",
      value: usd(oneOff),
      basis: `Central value: ${formatValue(months, "months_of_salary")} of salary per affected employee`,
    },
    ...funding(oneOff, decision.financing),
  ];
}

function acquisition(
  decision: Extract<Decision, { type: "acquisition" }>,
  facts: CutoffFacts,
): ResolvedLine[] {
  const price = decision.magnitude.value;
  const dealCosts = mul(price, decision.deal_cost_fraction);
  const uses = add(price, dealCosts);
  const debt = mul(uses, decision.financing.debt);
  const lines: ResolvedLine[] = [
    { label: "Purchase price", value: usd(price), basis: "Enterprise value paid" },
    {
      label: "Deal costs",
      value: usd(dealCosts),
      basis: `${formatValue(decision.deal_cost_fraction, "fraction")} of the price`,
    },
    {
      label: "Total funding need",
      value: usd(uses),
      basis: "Price plus deal costs: sources equal uses",
    },
    ...funding(uses, decision.financing),
  ];
  if (!isZero(decision.financing.debt)) {
    lines.push({
      label: "Yearly interest on new debt",
      value: usd(mul(debt, decision.new_debt_interest_rate)),
      basis: `${formatValue(decision.new_debt_interest_rate, "fraction")} a year`,
    });
  }
  lines.push({
    label: "Target EBITDA per year",
    value: usd(mul(decision.target_revenue, decision.target_ebitda_margin), true),
    basis: `${formatValue(decision.target_ebitda_margin, "fraction")} of ${formatUsd(decision.target_revenue)} revenue`,
  });
  const revenue = facts.revenue.value;
  if (revenue !== null && !isZero(revenue)) {
    lines.push({
      label: "Price relative to the buyer's yearly revenue",
      value: `${toDecimalString(div(price, revenue, 2))}×`,
      basis: basisOf(facts.revenue, "Revenue"),
    });
  }
  return lines;
}

function divestiture(
  decision: Extract<Decision, { type: "divestiture" }>,
  facts: CutoffFacts,
): ResolvedLine[] {
  const revenue = facts.revenue.value;
  if (revenue === null) return [];
  const leaving = mul(revenue, decision.magnitude.value);
  const proceeds = decision.disposal_proceeds;
  const lines: ResolvedLine[] = [
    {
      label: "Revenue that leaves per year",
      value: usd(leaving),
      basis: basisOf(facts.revenue, "Revenue"),
    },
    {
      label: "EBITDA that leaves per year",
      value: usd(mul(leaving, decision.segment_ebitda_margin), true),
      basis: `${formatValue(decision.segment_ebitda_margin, "fraction")} margin (assumption)`,
    },
    {
      label: "One-off separation cost",
      value: usd(mul(leaving, decision.separation_cost_fraction)),
      basis: `${formatValue(decision.separation_cost_fraction, "fraction")} of the unit's revenue`,
    },
    {
      label: "Sale proceeds",
      value: usd(proceeds),
      basis: isZero(proceeds) ? "Closure without a buyer" : "Before tax on the gain",
    },
  ];
  if (!isZero(proceeds)) {
    const {
      debt_paydown: paydown,
      cash_retained: kept,
      shareholder_distribution: returned,
    } = decision.use_of_proceeds;
    for (const [label, share] of [
      ["Debt paid down", paydown],
      ["Kept as cash", kept],
      ["Returned to shareholders", returned],
    ] as const) {
      if (!isZero(share)) {
        lines.push({
          label,
          value: usd(mul(proceeds, share)),
          basis: `${formatValue(share, "fraction")} of the proceeds, before tax`,
        });
      }
    }
  }
  return lines;
}

function capex(
  decision: Extract<Decision, { type: "capex_expansion" }>,
  facts: CutoffFacts,
): ResolvedLine[] {
  const amount = decision.magnitude.value;
  const lines: ResolvedLine[] = [
    { label: "Investment", value: usd(amount), basis: "Total capital expenditure" },
    {
      label: "Yearly depreciation once in use",
      value: usd(div(amount, String(decision.useful_life_years), 0)),
      basis: `Straight-line over ${decision.useful_life_years} years`,
    },
    ...funding(dec0(amount), decision.financing),
  ];
  if (!isZero(decision.financing.debt)) {
    lines.push({
      label: "Yearly interest on new debt",
      value: usd(mul(mul(amount, decision.financing.debt), decision.new_debt_interest_rate)),
      basis: `${formatValue(decision.new_debt_interest_rate, "fraction")} a year`,
    });
  }
  const revenue = facts.revenue.value;
  if (revenue !== null && !isZero(revenue)) {
    lines.push({
      label: "Investment relative to yearly revenue",
      value: formatValue(toDecimalString(div(amount, revenue, 4)), "fraction"),
      basis: basisOf(facts.revenue, "Revenue"),
    });
  }
  return lines;
}

function dec0(value: string): Dec {
  return div(value, "1", 0);
}

function refinance(decision: Extract<Decision, { type: "debt_refinance" }>): ResolvedLine[] {
  const amount = decision.magnitude.value;
  const newRate = central(decision, "new_interest_rate");
  const change = mul(amount, sub(newRate, decision.current_interest_rate));
  return [
    { label: "Amount refinanced", value: usd(amount), basis: "Principal replaced" },
    {
      label: "Change in yearly interest",
      value: usd(change, true),
      basis: `Central new rate ${formatValue(newRate, "fraction")} against ${formatValue(decision.current_interest_rate, "fraction")} today`,
    },
    {
      label: "One-off fees",
      value: usd(mul(amount, decision.refinancing_fee_fraction)),
      basis: `${formatValue(decision.refinancing_fee_fraction, "fraction")} of the amount`,
    },
  ];
}

/** The decision in dollars at its cutoff; empty when a needed figure is unknown. */
export function resolveDecision(draft: ScenarioDraft, facts: CutoffFacts): ResolvedLine[] {
  const { decision } = draft;
  const unitSpec = unitSpecFor(specFor(decision.type), decision.magnitude.unit);
  const size: ResolvedLine[] = unitSpec
    ? [
        {
          label: "Decision",
          value: formatMagnitude(decision.magnitude.value, unitSpec),
          basis: specFor(decision.type).label,
        },
      ]
    : [];
  switch (decision.type) {
    case "rnd_change":
      return [...size, ...rnd(decision, facts)];
    case "workforce_restructure":
      return [...size, ...workforce(decision, facts)];
    case "acquisition":
      return acquisition(decision, facts);
    case "divestiture":
      return [...size, ...divestiture(decision, facts)];
    case "capex_expansion":
      return capex(decision, facts);
    case "debt_refinance":
      return refinance(decision);
  }
}
