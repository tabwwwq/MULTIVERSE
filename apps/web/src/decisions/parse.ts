import type { ScenarioDraft } from "@multiverse/contracts";
import { CATALOG, isDecisionType, MAGNITUDE_UNITS, specFor } from "@/decisions/catalog";
import { checkRules, error, type Issue, type LooseDraft } from "@/decisions/rules";
import { isDecimal } from "@/lib/decimal";

/*
 * Structural check of a scenario draft read from JSON, mirroring what Pydantic does in
 * strict mode. Codes follow Pydantic's error types (missing, extra_forbidden,
 * string_type, int_type, string_pattern_mismatch, enum, union_tag_invalid, dict_type,
 * list_type) so shared fixtures expect the same code in both languages.
 */

type Json = Record<string, unknown>;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SEMVER = /^\d+\.\d+\.\d+$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHAPES: Record<string, readonly string[]> = {
  fixed: ["value"],
  uniform: ["low", "high"],
  triangular: ["low", "mode", "high"],
};

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRealDate(value: string): boolean {
  if (!DATE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

class Reader {
  readonly issues: Issue[] = [];

  object(
    value: unknown,
    path: string,
    required: readonly string[],
    optional: readonly string[] = [],
  ): Json | null {
    if (!isObject(value)) {
      this.issues.push(error("dict_type", path, "Expected an object."));
      return null;
    }
    const prefix = path ? `${path}.` : "";
    for (const key of required) {
      if (!(key in value)) this.issues.push(error("missing", `${prefix}${key}`, "Field required."));
    }
    for (const key of Object.keys(value)) {
      if (!required.includes(key) && !optional.includes(key)) {
        this.issues.push(error("extra_forbidden", `${prefix}${key}`, "Unknown field."));
      }
    }
    return value;
  }

  string(value: unknown, path: string, pattern?: RegExp): void {
    if (value === undefined) return;
    if (typeof value !== "string") {
      this.issues.push(error("string_type", path, "Expected a string."));
    } else if (pattern && !pattern.test(value)) {
      this.issues.push(error("string_pattern_mismatch", path, "Unexpected format."));
    }
  }

  decimal(value: unknown, path: string): void {
    if (value === undefined) return;
    if (typeof value !== "string") {
      this.issues.push(error("string_type", path, "Amounts are decimal strings, not numbers."));
    } else if (!isDecimal(value)) {
      this.issues.push(error("string_pattern_mismatch", path, "Not a decimal number."));
    }
  }

  integer(value: unknown, path: string): void {
    if (value === undefined) return;
    if (typeof value !== "number" || !Number.isInteger(value)) {
      this.issues.push(error("int_type", path, "Expected a whole number."));
    }
  }

  date(value: unknown, path: string): void {
    if (value === undefined) return;
    if (typeof value !== "string" || !isRealDate(value)) {
      this.issues.push(error("date_parsing", path, "Expected a date as YYYY-MM-DD."));
    }
  }

  oneOf(value: unknown, path: string, allowed: readonly string[]): void {
    if (value === undefined) return;
    if (typeof value !== "string" || !allowed.includes(value)) {
      this.issues.push(error("enum", path, `Expected one of: ${allowed.join(", ")}.`));
    }
  }

  distribution(value: unknown, path: string): void {
    if (!isObject(value)) {
      if (value !== undefined) this.issues.push(error("dict_type", path, "Expected an object."));
      return;
    }
    const shape = value["shape"];
    const points = typeof shape === "string" ? SHAPES[shape] : undefined;
    if (!points) {
      this.issues.push(
        error("union_tag_invalid", `${path}.shape`, "Use fixed, uniform or triangular."),
      );
      return;
    }
    this.object(value, path, ["shape", ...points]);
    for (const point of points) this.decimal(value[point], `${path}.${point}`);
  }
}

function readDecision(reader: Reader, value: unknown): void {
  if (!isObject(value)) {
    reader.issues.push(error("dict_type", "decision", "Expected an object."));
    return;
  }
  const type = value["type"];
  if (!isDecisionType(type)) {
    reader.issues.push(
      error("union_tag_invalid", "decision.type", "Not one of the six decision types."),
    );
    return;
  }
  const spec = specFor(type);
  const keys = [
    "type",
    "magnitude",
    "timing",
    ...spec.parameters.map((parameter) => parameter.key),
    ...(spec.share_group ? [spec.share_group.key] : []),
  ];
  reader.object(value, "decision", keys);

  const magnitude = value["magnitude"];
  if (
    magnitude !== undefined &&
    reader.object(magnitude, "decision.magnitude", ["value", "unit"])
  ) {
    const record = magnitude as Json;
    reader.decimal(record["value"], "decision.magnitude.value");
    reader.oneOf(record["unit"], "decision.magnitude.unit", MAGNITUDE_UNITS);
  }
  const timing = value["timing"];
  const timingKeys = ["announcement_date", "effective_date", "lag_quarters", "ramp_quarters"];
  if (timing !== undefined && reader.object(timing, "decision.timing", timingKeys)) {
    const record = timing as Json;
    reader.date(record["announcement_date"], "decision.timing.announcement_date");
    reader.date(record["effective_date"], "decision.timing.effective_date");
    reader.integer(record["lag_quarters"], "decision.timing.lag_quarters");
    reader.integer(record["ramp_quarters"], "decision.timing.ramp_quarters");
  }
  for (const parameter of spec.parameters) {
    const path = `decision.${parameter.key}`;
    const raw = value[parameter.key];
    if (parameter.uncertain) reader.distribution(raw, path);
    else if (parameter.integer) reader.integer(raw, path);
    else reader.decimal(raw, path);
  }
  const group = spec.share_group;
  if (group && value[group.key] !== undefined) {
    const members = group.members.map((member) => member.key);
    if (reader.object(value[group.key], `decision.${group.key}`, members)) {
      const record = value[group.key] as Json;
      for (const member of members)
        reader.decimal(record[member], `decision.${group.key}.${member}`);
    }
  }
}

export interface ParsedDraft {
  draft: ScenarioDraft | null;
  issues: Issue[];
}

/** Structure first; rules only for a structurally valid draft, as Pydantic does. */
export function parseScenarioDraft(input: unknown): ParsedDraft {
  const reader = new Reader();
  const keys = [
    "contracts_version",
    "company_id",
    "as_of",
    "data_origin",
    "horizon_quarters",
    "seed",
    "decision",
  ];
  const root = reader.object(input, "", keys, ["sensitivity"]);
  if (!root) return { draft: null, issues: reader.issues };

  reader.string(root["contracts_version"], "contracts_version", SEMVER);
  reader.string(root["company_id"], "company_id", UUID);
  reader.date(root["as_of"], "as_of");
  reader.oneOf(root["data_origin"], "data_origin", ["empirical", "synthetic"]);
  reader.integer(root["horizon_quarters"], "horizon_quarters");
  reader.integer(root["seed"], "seed");
  const seed = root["seed"];
  if (typeof seed === "number" && Number.isInteger(seed) && (seed < 0 || seed > 2 ** 31 - 1)) {
    reader.issues.push(error("out_of_range", "seed", "The seed is 0 to 2147483647."));
  }
  if (root["decision"] !== undefined) readDecision(reader, root["decision"]);

  const sensitivity = root["sensitivity"];
  if (sensitivity !== undefined) {
    const record = reader.object(sensitivity, "sensitivity", [], ["parameters", "points"]);
    if (record) {
      const parameters = record["parameters"];
      if (
        parameters !== undefined &&
        (!Array.isArray(parameters) || parameters.some((item) => typeof item !== "string"))
      ) {
        reader.issues.push(
          error("list_type", "sensitivity.parameters", "Expected a list of names."),
        );
      }
      reader.integer(record["points"], "sensitivity.points");
    }
  }
  if (reader.issues.length > 0) return { draft: null, issues: reader.issues };

  const draft = {
    ...root,
    sensitivity: {
      parameters: [],
      points: CATALOG.default_sensitivity_points,
      ...(isObject(sensitivity) ? sensitivity : {}),
    },
  } as unknown as ScenarioDraft;
  const issues = checkRules(draft as unknown as LooseDraft);
  return { draft: issues.length === 0 ? draft : null, issues };
}
