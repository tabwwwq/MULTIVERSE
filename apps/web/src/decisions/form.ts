import type {
  DataOrigin,
  InterventionSpec,
  MagnitudeUnit,
  ParameterSpec,
  ScenarioDraft,
} from "@multiverse/contracts";
import type { DecisionType, Distribution } from "@multiverse/contracts/interventions";
import { CATALOG, specFor, timingSpecs, unitSpecFor } from "@/decisions/catalog";
import { error, type Issue, type LooseDecision, type LooseDraft } from "@/decisions/rules";
import { fromInput, toInput } from "@/decisions/units";
import { parseUserDecimal } from "@/lib/decimal";

/*
 * What the form holds: text as typed, in display units (percent, USD millions). The
 * contract draft is derived from it; reading a field can fail ("abc"), and such a
 * field becomes undefined in the draft so the other rules still run.
 */

export interface DistributionField {
  shape: Distribution["shape"];
  value: string;
  low: string;
  mode: string;
  high: string;
}

export interface DecisionForm {
  type: DecisionType;
  magnitude: { value: string; unit: MagnitudeUnit | "" };
  timing: {
    announcement_date: string;
    effective_date: string;
    lag_quarters: string;
    ramp_quarters: string;
  };
  scalars: Record<string, string>;
  distributions: Record<string, DistributionField>;
  shares: Record<string, string>;
  sensitivity: { parameters: string[]; points: string };
}

export interface ScenarioForm {
  /** Version of the contract the draft was written in; kept on a round trip (Stage 07 migrations). */
  contracts_version: string;
  company_id: string;
  as_of: string;
  data_origin: DataOrigin;
  horizon_quarters: string;
  seed: number;
  decision: DecisionForm;
}

export function dayAfter(isoDate: string): string {
  const next = new Date(`${isoDate}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return next.toISOString().slice(0, 10);
}

function distributionField(distribution: Distribution, spec: ParameterSpec): DistributionField {
  const show = (value: string) => toInput(value, spec.unit);
  const field: DistributionField = {
    shape: distribution.shape,
    value: "",
    low: "",
    mode: "",
    high: "",
  };
  if (distribution.shape === "fixed") return { ...field, value: show(distribution.value) };
  if (distribution.shape === "uniform") {
    return { ...field, low: show(distribution.low), high: show(distribution.high) };
  }
  return {
    ...field,
    low: show(distribution.low),
    mode: show(distribution.mode),
    high: show(distribution.high),
  };
}

/** Documented defaults of a decision type (PRD FR-DE-07). The R&D unit stays unchosen. */
export function defaultDecisionForm(type: DecisionType, asOf: string): DecisionForm {
  const spec = specFor(type);
  const unit = spec.magnitude.default_unit;
  const unitSpec = unitSpecFor(spec, unit ?? undefined);
  const scalars: Record<string, string> = {};
  const distributions: Record<string, DistributionField> = {};
  for (const parameter of spec.parameters) {
    const value = parameter.default;
    if (typeof value === "string") scalars[parameter.key] = toInput(value, parameter.unit);
    else distributions[parameter.key] = distributionField(value, parameter);
  }
  const shares: Record<string, string> = {};
  spec.share_group?.members.forEach((member, index) => {
    shares[member.key] = toInput(spec.share_group?.defaults[index] ?? "0", "fraction");
  });
  return {
    type,
    magnitude: {
      value: unitSpec ? toInput(unitSpec.default_value, unitSpec.value_unit) : "",
      unit: unit ?? "",
    },
    timing: {
      announcement_date: asOf,
      effective_date: dayAfter(asOf),
      lag_quarters: String(spec.lag_quarters.default),
      ramp_quarters: String(spec.ramp_quarters.default),
    },
    scalars,
    distributions,
    shares,
    sensitivity: { parameters: [], points: String(CATALOG.default_sensitivity_points) },
  };
}

export function defaultScenarioForm(
  companyId: string,
  asOf: string,
  type: DecisionType,
  dataOrigin: DataOrigin,
): ScenarioForm {
  return {
    contracts_version: CATALOG.contracts_version,
    company_id: companyId,
    as_of: asOf,
    data_origin: dataOrigin,
    horizon_quarters: String(CATALOG.horizon_quarters.default),
    seed: CATALOG.default_seed,
    decision: defaultDecisionForm(type, asOf),
  };
}

/** Moves untouched default dates along when the cutoff changes. */
export function moveDefaultDates(form: DecisionForm, from: string, to: string): DecisionForm {
  const { timing } = form;
  if (timing.announcement_date !== from || timing.effective_date !== dayAfter(from)) return form;
  return { ...form, timing: { ...timing, announcement_date: to, effective_date: dayAfter(to) } };
}

class FieldReader {
  readonly issues: Issue[] = [];

  /** Typed text to a contract decimal in `unit`, or undefined with an issue. */
  decimal(text: string, path: string, unit: ParameterSpec["unit"]): string | undefined {
    if (text.trim() === "") {
      this.issues.push(error("required", path, "Enter a value."));
      return undefined;
    }
    const parsed = parseUserDecimal(text);
    if (parsed === null) {
      this.issues.push(error("not_a_number", path, "Enter a number, for example 40 or −12.5."));
      return undefined;
    }
    return fromInput(parsed, unit);
  }

  integer(text: string, path: string): number | undefined {
    const parsed = this.decimal(text, path, "quarters");
    if (parsed === undefined) return undefined;
    if (!/^-?\d+$/.test(parsed)) {
      this.issues.push(error("not_integer", path, "Enter a whole number."));
      return undefined;
    }
    return Number(parsed);
  }

  date(text: string, path: string): string | undefined {
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
    this.issues.push(error("required", path, "Enter a date."));
    return undefined;
  }
}

function readParameter(reader: FieldReader, form: DecisionForm, spec: ParameterSpec): unknown {
  const path = `decision.${spec.key}`;
  if (!spec.uncertain) {
    const text = form.scalars[spec.key] ?? "";
    return spec.integer ? reader.integer(text, path) : reader.decimal(text, path, spec.unit);
  }
  const field = form.distributions[spec.key];
  if (!field) return undefined;
  const point = (name: "value" | "low" | "mode" | "high") =>
    reader.decimal(field[name], `${path}.${name}`, spec.unit);
  if (field.shape === "fixed") return { shape: "fixed", value: point("value") };
  if (field.shape === "uniform")
    return { shape: "uniform", low: point("low"), high: point("high") };
  return { shape: "triangular", low: point("low"), mode: point("mode"), high: point("high") };
}

export interface ReadForm {
  draft: LooseDraft;
  issues: Issue[];
}

/** The contract draft behind a form, with an issue for every field that cannot be read. */
export function readScenarioForm(form: ScenarioForm): ReadForm {
  const reader = new FieldReader();
  const decisionForm = form.decision;
  const spec: InterventionSpec = specFor(decisionForm.type);

  const unit = decisionForm.magnitude.unit;
  const unitSpec = unitSpecFor(spec, unit || undefined);
  let magnitudeValue: string | undefined;
  if (unit === "") {
    reader.issues.push(
      error(
        "unit_required",
        "decision.magnitude.unit",
        "Choose what the number is measured against: it changes what the decision means.",
      ),
    );
    if (decisionForm.magnitude.value.trim() === "") {
      reader.issues.push(error("required", "decision.magnitude.value", "Enter a value."));
    } else if (parseUserDecimal(decisionForm.magnitude.value) === null) {
      reader.issues.push(
        error("not_a_number", "decision.magnitude.value", "Enter a number, for example 40."),
      );
    }
  } else {
    magnitudeValue = reader.decimal(
      decisionForm.magnitude.value,
      "decision.magnitude.value",
      unitSpec?.value_unit ?? "fraction",
    );
  }

  const decision: LooseDecision = {
    type: decisionForm.type,
    magnitude: { value: magnitudeValue, unit: unit || undefined },
    timing: {
      announcement_date: reader.date(
        decisionForm.timing.announcement_date,
        "decision.timing.announcement_date",
      ),
      effective_date: reader.date(
        decisionForm.timing.effective_date,
        "decision.timing.effective_date",
      ),
      lag_quarters: undefined,
      ramp_quarters: undefined,
    },
  };
  for (const timing of timingSpecs(spec)) {
    const key = timing.key as "lag_quarters" | "ramp_quarters";
    decision.timing[key] = reader.integer(decisionForm.timing[key], `decision.timing.${key}`);
  }
  for (const parameter of spec.parameters) {
    decision[parameter.key] = readParameter(reader, decisionForm, parameter);
  }
  const group = spec.share_group;
  if (group) {
    const shares: Record<string, string | undefined> = {};
    for (const member of group.members) {
      shares[member.key] = reader.decimal(
        decisionForm.shares[member.key] ?? "",
        `decision.${group.key}.${member.key}`,
        "fraction",
      );
    }
    decision[group.key] = shares;
  }

  const sensitivityPoints = Number(decisionForm.sensitivity.points);
  const draft: LooseDraft = {
    as_of: form.as_of,
    horizon_quarters: reader.integer(form.horizon_quarters, "horizon_quarters"),
    decision,
    sensitivity: {
      parameters: decisionForm.sensitivity.parameters,
      points: Number.isInteger(sensitivityPoints) ? sensitivityPoints : undefined,
    },
  };
  return { draft, issues: reader.issues };
}

function hasUndefined(value: unknown): boolean {
  if (value === undefined) return true;
  if (typeof value !== "object" || value === null) return false;
  return Object.values(value).some(hasUndefined);
}

/** A complete contract draft, or null while any field cannot be read. */
export function toScenarioDraft(form: ScenarioForm, read: ReadForm): ScenarioDraft | null {
  if (read.issues.length > 0 || hasUndefined(read.draft)) return null;
  const { decision } = read.draft;
  const spec = specFor(decision.type);
  // Contract field order, so the JSON matches what the Python contracts serialize.
  const ordered: Record<string, unknown> = {
    magnitude: decision.magnitude,
    timing: decision.timing,
    type: decision.type,
  };
  for (const parameter of spec.parameters) ordered[parameter.key] = decision[parameter.key];
  if (spec.share_group) ordered[spec.share_group.key] = decision[spec.share_group.key];
  return {
    contracts_version: form.contracts_version,
    company_id: form.company_id,
    as_of: form.as_of,
    data_origin: form.data_origin,
    horizon_quarters: read.draft.horizon_quarters ?? 0,
    seed: form.seed,
    decision: ordered as unknown as ScenarioDraft["decision"],
    sensitivity: {
      parameters: [...read.draft.sensitivity.parameters],
      points: read.draft.sensitivity.points ?? CATALOG.default_sensitivity_points,
    },
  };
}

/** The form that produces a given draft (JSON round trip, restore in Stage 07). */
export function scenarioFormFromDraft(draft: ScenarioDraft): ScenarioForm {
  const decision = draft.decision as unknown as Record<string, unknown> & ScenarioDraft["decision"];
  const spec = specFor(draft.decision.type);
  const unitSpec = unitSpecFor(spec, decision.magnitude.unit);
  const base = defaultDecisionForm(draft.decision.type, draft.as_of);
  const scalars: Record<string, string> = {};
  const distributions: Record<string, DistributionField> = {};
  for (const parameter of spec.parameters) {
    const value = decision[parameter.key];
    if (parameter.uncertain) {
      distributions[parameter.key] = distributionField(value as Distribution, parameter);
    } else {
      scalars[parameter.key] = toInput(String(value), parameter.unit);
    }
  }
  const shares: Record<string, string> = {};
  if (spec.share_group) {
    const group = decision[spec.share_group.key] as Record<string, string>;
    for (const member of spec.share_group.members) {
      shares[member.key] = toInput(group[member.key] ?? "0", "fraction");
    }
  }
  return {
    contracts_version: draft.contracts_version,
    company_id: draft.company_id,
    as_of: draft.as_of,
    data_origin: draft.data_origin,
    horizon_quarters: String(draft.horizon_quarters),
    seed: draft.seed,
    decision: {
      ...base,
      magnitude: {
        value: toInput(decision.magnitude.value, unitSpec?.value_unit ?? "fraction"),
        unit: decision.magnitude.unit,
      },
      timing: {
        announcement_date: decision.timing.announcement_date,
        effective_date: decision.timing.effective_date,
        lag_quarters: String(decision.timing.lag_quarters),
        ramp_quarters: String(decision.timing.ramp_quarters),
      },
      scalars,
      distributions,
      shares,
      sensitivity: {
        parameters: [...draft.sensitivity.parameters],
        points: String(draft.sensitivity.points),
      },
    },
  };
}
