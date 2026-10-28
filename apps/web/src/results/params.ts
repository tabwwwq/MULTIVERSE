import type { ResultMetric } from "@multiverse/contracts";
import type { RawParams } from "@/companies/params";
import type { ChartMode } from "@/results/series";

/* Link parameters of result pages: allowlisted, rejected names reported, values never echoed. */

const METRICS: readonly ResultMetric[] = ["revenue", "ebitda", "fcf", "net_debt", "ev"];
const MODES: readonly ChartMode[] = ["absolute", "change", "percent"];

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export interface ParsedResultParams {
  metric: ResultMetric;
  mode: ChartMode;
  compareWith: string | null;
  ignored: string[];
}

export function parseResultParams(
  raw: RawParams,
  knownResults: readonly string[],
): ParsedResultParams {
  const ignored: string[] = [];
  const metric = first(raw["metric"]);
  const mode = first(raw["mode"]);
  const other = first(raw["with"]);
  const pick = <T extends string>(
    name: string,
    value: string | undefined,
    allowed: readonly T[],
    fallback: T,
  ): T => {
    if (value === undefined || value === "") return fallback;
    if ((allowed as readonly string[]).includes(value)) return value as T;
    ignored.push(name);
    return fallback;
  };
  const parsedMetric = pick("metric", metric, METRICS, "revenue");
  const parsedMode = pick("mode", mode, MODES, "absolute");
  let compareWith: string | null = null;
  if (other !== undefined && other !== "") {
    if (knownResults.includes(other)) compareWith = other;
    else ignored.push("with");
  }
  return {
    metric: parsedMetric,
    mode: parsedMode,
    compareWith,
    ignored,
  };
}
