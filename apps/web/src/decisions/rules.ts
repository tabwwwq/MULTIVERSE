import type { InterventionSpec, ParameterSpec, ValueRange } from "@multiverse/contracts";
import type { DecisionType, Distribution } from "@multiverse/contracts/interventions";
import {
  CATALOG,
  formatMagnitude,
  parameterFor,
  specFor,
  timingSpecs,
  unitSpecFor,
} from "@/decisions/catalog";
import { formatValue } from "@/decisions/units";
import { add, compare, isZero, mul, shift, toDecimalString } from "@/lib/decimal";

/*
 * Contract rules of a scenario draft, mirrored from multiverse_contracts.decisions with
 * the same codes and paths. Shared fixtures run through both (ADR-0008). Unlike the
 * Python validator, which stops at the first violation, this one reports every issue,
 * and it skips the checks of a field the form could not read (undefined leaves).
 */

export type Severity = "error" | "warning";

export interface Issue {
  code: string;
  /** Contract path, e.g. "decision.financing.debt". */
  path: string;
  severity: Severity;
  message: string;
}

/** Contract-shaped draft whose leaves are undefined where the form had no readable value. */
export interface LooseDraft {
  as_of: string | undefined;
  horizon_quarters: number | undefined;
  decision: LooseDecision;
  sensitivity: { parameters: readonly string[]; points: number | undefined };
}

export interface LooseDecision {
  type: DecisionType;
  magnitude: { value: string | undefined; unit: string | undefined };
  timing: {
    announcement_date: string | undefined;
    effective_date: string | undefined;
    lag_quarters: number | undefined;
    ramp_quarters: number | undefined;
  };
  /** Scalars, distributions and share groups keyed by catalog key. */
  [key: string]: unknown;
}

export function error(code: string, path: string, message: string): Issue {
  return { code, path, severity: "error", message };
}

export function warning(code: string, path: string, message: string): Issue {
  return { code, path, severity: "warning", message };
}

/** Same day `quarters` * 3 months later, clamped to the end of a shorter month. */
export function addQuarters(isoDate: string, quarters: number): string {
  const [year = 0, month = 1, day = 1] = isoDate.split("-").map(Number);
  const months = month - 1 + 3 * quarters;
  const targetYear = year + Math.floor(months / 12);
  const targetMonth = (months % 12) + 1;
  const lastDay = new Date(Date.UTC(targetYear, targetMonth, 0)).getUTCDate();
  const iso = (n: number, width: number) => String(n).padStart(width, "0");
  return `${iso(targetYear, 4)}-${iso(targetMonth, 2)}-${iso(Math.min(day, lastDay), 2)}`;
}

export function inRange(value: string | number, range: ValueRange): boolean {
  const text = String(value);
  return compare(text, range.min) >= 0 && compare(text, range.max) <= 0;
}

function rangeText(range: ValueRange, format: (value: string) => string): string {
  return `${format(range.min)} to ${format(range.max)}`;
}

function checkNumber(
  value: string | number | undefined,
  spec: ParameterSpec,
  path: string,
  issues: Issue[],
): void {
  if (value === undefined || inRange(value, spec.allowed)) return;
  const format = (v: string) => formatValue(v, spec.unit);
  issues.push(
    error("out_of_range", path, `Enter a value from ${rangeText(spec.allowed, format)}.`),
  );
}

const POINTS: Record<Distribution["shape"], readonly ("value" | "low" | "mode" | "high")[]> = {
  fixed: ["value"],
  uniform: ["low", "high"],
  triangular: ["low", "mode", "high"],
};

export function distributionPoints(distribution: Distribution): string[] {
  const record = distribution as unknown as Record<string, string>;
  return POINTS[distribution.shape].map((name) => record[name] ?? "");
}

function checkDistribution(
  value: unknown,
  spec: ParameterSpec,
  path: string,
  issues: Issue[],
): void {
  if (value === undefined || value === null) return;
  const distribution = value as Distribution;
  const record = distribution as unknown as Record<string, string | undefined>;
  const names = POINTS[distribution.shape];
  const before = issues.length;
  for (const name of names) checkNumber(record[name], spec, `${path}.${name}`, issues);
  const points = names.map((name) => record[name]);
  if (issues.length > before || points.some((point) => point === undefined)) return;
  const values = points as string[];
  const ordered = values.every(
    (point, i) => i === 0 || compare(values[i - 1] ?? point, point) <= 0,
  );
  const spread = values.length === 1 || compare(values[0] ?? "0", values.at(-1) ?? "0") < 0;
  if (!ordered || !spread) {
    issues.push(
      error(
        "distribution_order",
        path,
        names.length === 3
          ? "Keep low ≤ most likely ≤ high, with low below high."
          : "Keep low below high.",
      ),
    );
  }
}

function percentText(total: string): string {
  return `${toDecimalString(shift(total, 2))}%`;
}

function checkShares(decision: LooseDecision, spec: InterventionSpec, issues: Issue[]): void {
  const group = spec.share_group;
  if (!group) return;
  const shares = (decision[group.key] ?? {}) as Record<string, string | undefined>;
  let total = "0";
  let complete = true;
  for (const member of group.members) {
    const share = shares[member.key];
    if (share === undefined) {
      complete = false;
      continue;
    }
    if (compare(share, "0") < 0 || compare(share, "1") > 0) {
      issues.push(
        error("out_of_range", `decision.${group.key}.${member.key}`, "Enter 0% to 100%."),
      );
      complete = false;
      continue;
    }
    total = toDecimalString(add(total, share));
  }
  if (!complete) return;
  if (compare(total, "1") !== 0) {
    issues.push(
      error(
        "shares_sum",
        `decision.${group.key}`,
        `${group.label} shares add up to ${percentText(total)}. They must add up to exactly 100%.`,
      ),
    );
    return;
  }
  const rate = decision["new_debt_interest_rate"];
  const debt = shares["debt"];
  if (debt !== undefined && compare(debt, "0") > 0 && typeof rate === "string" && isZero(rate)) {
    issues.push(
      error(
        "rate_required",
        "decision.new_debt_interest_rate",
        "New debt needs an interest rate above 0%.",
      ),
    );
  }
}

function checkDecision(decision: LooseDecision, issues: Issue[]): void {
  const spec = specFor(decision.type);
  const { value, unit } = decision.magnitude;
  const unitSpec = unitSpecFor(spec, unit);
  if (unit !== undefined && !unitSpec) {
    issues.push(
      error(
        "unit_not_allowed",
        "decision.magnitude.unit",
        `${spec.label} is measured in ${spec.magnitude.units.map((u) => u.label).join(" or ")}.`,
      ),
    );
  }
  if (unitSpec && value !== undefined) {
    if (!inRange(value, unitSpec.allowed)) {
      const format = (v: string) => formatMagnitude(v, unitSpec);
      issues.push(
        error(
          "out_of_range",
          "decision.magnitude.value",
          `Enter a value from ${rangeText(unitSpec.allowed, format)}.`,
        ),
      );
    } else if (isZero(value)) {
      issues.push(
        error(
          "zero_magnitude",
          "decision.magnitude.value",
          "A decision of size 0 is the baseline. Enter a change.",
        ),
      );
    }
  }

  for (const timing of timingSpecs(spec)) {
    const key = timing.key as "lag_quarters" | "ramp_quarters";
    checkNumber(decision.timing[key], timing, `decision.timing.${key}`, issues);
  }
  for (const parameter of spec.parameters) {
    const path = `decision.${parameter.key}`;
    const raw = decision[parameter.key];
    if (parameter.uncertain) checkDistribution(raw, parameter, path, issues);
    else checkNumber(raw as string | number | undefined, parameter, path, issues);
  }
  checkShares(decision, spec, issues);
}

function checkScenario(draft: LooseDraft, issues: Issue[]): void {
  const { as_of: asOf, horizon_quarters: horizon } = draft;
  checkNumber(horizon, CATALOG.horizon_quarters, "horizon_quarters", issues);
  const horizonOk = horizon !== undefined && inRange(horizon, CATALOG.horizon_quarters.allowed);

  const {
    announcement_date: announced,
    effective_date: effective,
    lag_quarters: lag,
  } = draft.decision.timing;
  if (asOf !== undefined && announced !== undefined && announced < asOf) {
    issues.push(
      error(
        "announcement_before_cutoff",
        "decision.timing.announcement_date",
        `A decision made at the cutoff ${asOf} cannot be announced before it.`,
      ),
    );
  }
  if (announced !== undefined && effective !== undefined && effective < announced) {
    issues.push(
      error(
        "effective_before_announcement",
        "decision.timing.effective_date",
        "The effective date cannot come before the announcement.",
      ),
    );
  }
  if (asOf !== undefined && horizonOk && effective !== undefined) {
    const horizonEnd = addQuarters(asOf, horizon);
    if (effective >= horizonEnd) {
      issues.push(
        error(
          "effect_after_horizon",
          "decision.timing.effective_date",
          `The effective date must fall before the end of the horizon, ${horizonEnd}.`,
        ),
      );
    } else if (lag !== undefined && addQuarters(effective, lag) >= horizonEnd) {
      issues.push(
        error(
          "effect_after_horizon",
          "decision.timing.lag_quarters",
          `The effect would start after the end of the horizon, ${horizonEnd}.`,
        ),
      );
    }
  }
}

function checkSensitivity(draft: LooseDraft, issues: Issue[]): void {
  const { parameters, points } = draft.sensitivity;
  const path = "sensitivity.parameters";
  if (points !== undefined && !CATALOG.sensitivity_points.includes(points)) {
    issues.push(
      error("sensitivity_points", "sensitivity.points", "Use 3, 5 or 7 points per parameter."),
    );
  }
  if (parameters.length > CATALOG.sensitivity_max_parameters) {
    issues.push(
      error(
        "sensitivity_too_many",
        path,
        `Choose at most ${CATALOG.sensitivity_max_parameters} parameters.`,
      ),
    );
    return;
  }
  if (new Set(parameters).size !== parameters.length) {
    issues.push(error("sensitivity_duplicate", path, "Choose each parameter at most once."));
    return;
  }
  const spec = specFor(draft.decision.type);
  for (const key of parameters) {
    const parameter = parameterFor(spec, key);
    if (!parameter?.uncertain) {
      issues.push(error("sensitivity_unknown", path, `${key} is not an uncertain parameter.`));
      continue;
    }
    const distribution = draft.decision[key] as Distribution | undefined;
    if (distribution?.shape === "fixed") {
      issues.push(
        error(
          "sensitivity_fixed",
          path,
          `${parameter.label} has a fixed value. Give it a range to vary it.`,
        ),
      );
    }
  }
}

/** Every contract rule the draft breaks, in form order. */
export function checkRules(draft: LooseDraft): Issue[] {
  const issues: Issue[] = [];
  checkScenario(draft, issues);
  checkDecision(draft.decision, issues);
  checkSensitivity(draft, issues);
  return issues;
}

/** Values outside the planning range: allowed, but any result is fictional exploratory. */
export function planningWarnings(draft: LooseDraft): Issue[] {
  const issues: Issue[] = [];
  const spec = specFor(draft.decision.type);
  const note = "Outside the planning range";
  const flag = (path: string, range: ValueRange, format: (v: string) => string) => {
    issues.push(
      warning(
        "out_of_distribution",
        path,
        `${note} (${rangeText(range, format)}). Any result for this value is fictional exploratory, not an estimate.`,
      ),
    );
  };

  const unitSpec = unitSpecFor(spec, draft.decision.magnitude.unit);
  const magnitude = draft.decision.magnitude.value;
  if (unitSpec?.planning && magnitude !== undefined && inRange(magnitude, unitSpec.allowed)) {
    if (!inRange(magnitude, unitSpec.planning)) {
      flag("decision.magnitude.value", unitSpec.planning, (v) => formatMagnitude(v, unitSpec));
    }
  }
  for (const parameter of spec.parameters) {
    const planning = parameter.planning;
    if (!planning) continue;
    const raw = draft.decision[parameter.key];
    const points = parameter.uncertain
      ? raw
        ? distributionPoints(raw as Distribution)
        : []
      : raw === undefined
        ? []
        : [String(raw)];
    const valid = points.filter((point) => point !== "" && inRange(point, parameter.allowed));
    if (valid.some((point) => !inRange(point, planning))) {
      flag(`decision.${parameter.key}`, planning, (v) => formatValue(v, parameter.unit));
    }
  }
  return issues;
}

/** Midpoint of a uniform range, mode of a triangular one, or the fixed value. */
export function centralValue(distribution: Distribution): string {
  if (distribution.shape === "fixed") return distribution.value;
  if (distribution.shape === "uniform") {
    return toDecimalString(mul(add(distribution.low, distribution.high), "0.5"));
  }
  return distribution.mode;
}
