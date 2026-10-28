import { specFor, unitSpecFor } from "@/decisions/catalog";
import {
  type BaseFigure,
  type CompanyContext,
  type CutoffFacts,
  MIN_QUARTERS,
} from "@/decisions/context";
import { addQuarters, error, type Issue, type LooseDraft, warning } from "@/decisions/rules";
import { formatUsd } from "@/decisions/units";
import { compare, mul } from "@/lib/decimal";

/*
 * Whether a decision fits the company at the cutoff (PRD FR-DE-06, FC-01 to FC-03).
 * The contract cannot know this: it needs the point-in-time dossier. The server-side
 * version arrives with POST /api/v1/scenarios/validate.
 *
 * The relative-size thresholds below are design defaults, like the planning ranges.
 */

const LARGE_DEAL_TO_REVENUE = "2";
const LARGE_CAPEX_TO_REVENUE = "1";

const BASE_LABELS = {
  previous_rnd_budget: "previous R&D budget",
  revenue: "revenue",
  headcount: "revenue",
  none: "",
} as const;

function baseFigure(base: keyof typeof BASE_LABELS, facts: CutoffFacts): BaseFigure | null {
  if (base === "previous_rnd_budget") return facts.rnd;
  if (base === "revenue" || base === "headcount") return facts.revenue;
  return null;
}

/** Issues that would apply to any decision for this company at this cutoff. */
export function companyIssues(context: CompanyContext, facts: CutoffFacts | undefined): Issue[] {
  if (context.supportStatus === "unsupported") {
    return [
      error(
        "company_unsupported",
        "company_id",
        `${context.name} is not supported: ${context.supportReason ?? "no usable data"}`,
      ),
    ];
  }
  if (!facts) {
    return [error("no_public_data", "as_of", "Choose a knowledge cutoff for this company.")];
  }
  const issues: Issue[] = [];
  if (facts.quartersPublic === 0) {
    issues.push(
      error(
        "no_public_data",
        "as_of",
        `No financial data was public by ${facts.asOf}. The first filing was published on ${context.firstFiled ?? "an unknown date"}.`,
      ),
    );
  } else if (facts.quartersPublic < MIN_QUARTERS) {
    issues.push(
      warning(
        "insufficient_history",
        "as_of",
        `Insufficient history: ${facts.quartersPublic} of the ${MIN_QUARTERS} quarters needed were public by ${facts.asOf}. Only demo runs are possible; empirical and causal modes stay blocked.`,
      ),
    );
  }
  return issues;
}

export function eligibilityIssues(
  draft: LooseDraft,
  context: CompanyContext,
  facts: CutoffFacts | undefined,
): Issue[] {
  const issues = companyIssues(context, facts);
  if (!facts || issues.some((issue) => issue.severity === "error")) return issues;

  const { decision } = draft;
  const spec = specFor(decision.type);
  const unitSpec = unitSpecFor(spec, decision.magnitude.unit);

  if (unitSpec && unitSpec.base !== "none") {
    const figure = baseFigure(unitSpec.base, facts);
    if (figure && figure.value === null) {
      issues.push(
        error(
          "base_unavailable",
          "decision.magnitude.unit",
          `A change measured against the ${BASE_LABELS[unitSpec.base]} needs that figure at ${facts.asOf}. ${figure.reason ?? ""}`.trim(),
        ),
      );
    }
  }

  const exit = context.status !== "active" ? context.statusDate : null;
  const effective = decision.timing.effective_date;
  if (exit && effective !== undefined && effective >= exit) {
    issues.push(
      error(
        "company_left_market",
        "decision.timing.effective_date",
        `${context.name} left the market on ${exit} (${context.status}). A decision cannot take effect after that.`,
      ),
    );
  } else if (
    exit &&
    draft.as_of !== undefined &&
    draft.horizon_quarters !== undefined &&
    addQuarters(draft.as_of, draft.horizon_quarters) > exit
  ) {
    issues.push(
      warning(
        "horizon_after_exit",
        "horizon_quarters",
        `${context.name} left the market on ${exit}. Quarters after that date have no observed history to compare with.`,
      ),
    );
  }

  if (
    decision.type === "rnd_change" &&
    facts.rnd.value === null &&
    decision.magnitude.unit !== "fraction_of_previous_rnd_budget"
  ) {
    issues.push(
      warning(
        "no_rnd_history",
        "decision.magnitude.value",
        `${context.name} reports no usable R&D history at ${facts.asOf}, so the decision has no comparable past behind it.`,
      ),
    );
  }

  const magnitude = decision.magnitude.value;
  const revenue = facts.revenue.value;
  if (magnitude !== undefined && revenue !== null) {
    if (
      decision.type === "acquisition" &&
      compare(magnitude, mul(revenue, LARGE_DEAL_TO_REVENUE)) > 0
    ) {
      issues.push(
        warning(
          "large_relative_deal",
          "decision.magnitude.value",
          `The price is more than ${LARGE_DEAL_TO_REVENUE}× the company's yearly revenue (${formatUsd(revenue)}). Funding and integration risks dominate such a deal.`,
        ),
      );
    }
    if (
      decision.type === "capex_expansion" &&
      compare(magnitude, mul(revenue, LARGE_CAPEX_TO_REVENUE)) > 0
    ) {
      issues.push(
        warning(
          "large_relative_capex",
          "decision.magnitude.value",
          `The investment is larger than the company's yearly revenue (${formatUsd(revenue)}).`,
        ),
      );
    }
  }

  if (decision.type === "divestiture") {
    issues.push(
      warning(
        "segment_data_unavailable",
        "decision.magnitude.value",
        "Segment figures are not in the demo data, so the size and margin of the unit are your assumptions.",
      ),
    );
  }
  if (decision.type === "debt_refinance") {
    const netDebt = facts.netDebt.value;
    if (netDebt !== null && compare(netDebt, "0") <= 0) {
      issues.push(
        warning(
          "net_cash_position",
          "decision.magnitude.value",
          `${context.name} held net cash at ${facts.asOf} (net debt ${formatUsd(netDebt)}). Gross debt is not in the demo data; check that there is debt to refinance.`,
        ),
      );
    }
  }
  const financing = decision["financing"] as Record<string, string | undefined> | undefined;
  const equity = financing?.["equity"];
  if (equity !== undefined && compare(equity, "0") > 0) {
    issues.push(
      warning(
        "dilution_not_modelled",
        "decision.financing",
        "New equity dilutes shareholders, but share counts are out of scope (decision D-06): dilution is not modelled.",
      ),
    );
  }
  return issues;
}
