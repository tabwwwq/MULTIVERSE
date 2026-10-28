import type {
  InterventionSpec,
  MagnitudeUnit,
  MagnitudeUnitSpec,
  ParameterSpec,
} from "@multiverse/contracts";
import { type DecisionType, INTERVENTION_CATALOG } from "@multiverse/contracts/interventions";
import { formatValue } from "@/decisions/units";
import type { DecimalInput } from "@/lib/decimal";

/** The catalog generated from the Python contracts (single source of every range). */
export const CATALOG = INTERVENTION_CATALOG;

export const DECISION_TYPES: readonly DecisionType[] = CATALOG.interventions.map(
  (spec) => spec.type,
);

export const MAGNITUDE_UNITS: readonly MagnitudeUnit[] = [
  "fraction_of_previous_rnd_budget",
  "pp_of_revenue",
  "fraction_of_headcount",
  "fraction_of_revenue",
  "usd",
];

export function isDecisionType(value: unknown): value is DecisionType {
  return typeof value === "string" && (DECISION_TYPES as readonly string[]).includes(value);
}

export function specFor(type: DecisionType): InterventionSpec {
  const spec = CATALOG.interventions.find((candidate) => candidate.type === type);
  if (!spec) throw new Error(`No catalog entry for ${type}`);
  return spec;
}

export function unitSpecFor(
  spec: InterventionSpec,
  unit: string | undefined,
): MagnitudeUnitSpec | undefined {
  return spec.magnitude.units.find((candidate) => candidate.unit === unit);
}

export function parameterFor(spec: InterventionSpec, key: string): ParameterSpec | undefined {
  return spec.parameters.find((parameter) => parameter.key === key);
}

/** Timing parameters, keyed like the contract fields. */
export function timingSpecs(spec: InterventionSpec): readonly ParameterSpec[] {
  return [spec.lag_quarters, spec.ramp_quarters];
}

/** "+40% of the previous R&D budget", "+2 p.p. of revenue", "USD 1.0bn". */
export function formatMagnitude(value: DecimalInput, unit: MagnitudeUnitSpec): string {
  const signed = unit.value_unit !== "usd";
  const amount = formatValue(value, unit.value_unit, signed);
  if (unit.value_unit === "fraction") return `${amount} ${unit.label.replace(/^% /, "")}`;
  if (unit.value_unit === "percentage_points") {
    return `${amount} ${unit.label.replace(/^percentage points /, "")}`;
  }
  return amount;
}
