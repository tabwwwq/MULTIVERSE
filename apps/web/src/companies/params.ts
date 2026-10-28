import type { CompanyStatus, Sector } from "@multiverse/contracts";
import { COMPANY_STATUSES, SECTORS } from "@/companies/labels";
import { MAX_QUERY_LENGTH, normalizeQuery } from "@/companies/search";

/*
 * Safe URL handling: every query parameter is checked against an allowlist or a
 * strict pattern. Invalid values are dropped and reported by parameter name only;
 * the raw value is never echoed back, so a crafted link cannot inject text.
 */

export type RawParams = Record<string, string | string[] | undefined>;

export type CoverageFilter = "12-plus" | "8-plus" | "under-8";

export const COVERAGE_FILTERS: Record<CoverageFilter, string> = {
  "12-plus": "12 quarters or more",
  "8-plus": "8 quarters or more",
  "under-8": "Fewer than 8 quarters",
};

export interface ExplorerQuery {
  q: string;
  sector: Sector | null;
  country: string | null;
  status: CompanyStatus | null;
  coverage: CoverageFilter | null;
}

export interface ParsedExplorerParams {
  query: ExplorerQuery;
  /** Names of parameters whose values were not accepted. */
  ignored: string[];
  /** The search text was longer than MAX_QUERY_LENGTH and was shortened. */
  shortened: boolean;
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function oneOf<T extends string>(value: string | undefined, allowed: readonly T[]): T | null {
  return value !== undefined && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : null;
}

export function parseExplorerParams(raw: RawParams): ParsedExplorerParams {
  const ignored: string[] = [];
  const check = <T>(name: string, value: string | undefined, parsed: T | null): T | null => {
    if (value !== undefined && value !== "" && parsed === null) ignored.push(name);
    return parsed;
  };

  const rawQuery = first(raw["q"]) ?? "";
  const q = normalizeQuery(rawQuery);
  const sector = first(raw["sector"]);
  const country = first(raw["country"]);
  const status = first(raw["status"]);
  const coverage = first(raw["coverage"]);

  return {
    query: {
      q,
      sector: check("sector", sector, oneOf(sector, SECTORS)),
      country: check("country", country, country && /^[A-Z]{2}$/.test(country) ? country : null),
      status: check("status", status, oneOf(status, COMPANY_STATUSES)),
      coverage: check(
        "coverage",
        coverage,
        oneOf(coverage, Object.keys(COVERAGE_FILTERS) as CoverageFilter[]),
      ),
    },
    ignored,
    shortened: rawQuery.trim().length > MAX_QUERY_LENGTH,
  };
}

/** Builds an explorer URL from accepted values only. */
export function explorerHref(query: Partial<ExplorerQuery>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (typeof value === "string" && value !== "") params.set(key, value);
  }
  const search = params.toString();
  return search ? `/universe?${search}` : "/universe";
}

export type Scale = "m" | "bn";

export interface ParsedDossierParams {
  /** Knowledge cutoff chosen by the user (YYYY-MM-DD), or null for the latest snapshot. */
  asOf: string | null;
  scale: Scale;
  ignored: string[];
}

function isRealDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

/** `latestCutoff` is the dossier's own as_of date: a user cannot look past the snapshot. */
export function parseDossierParams(raw: RawParams, latestCutoff: string): ParsedDossierParams {
  const ignored: string[] = [];
  const asOfRaw = first(raw["asOf"]);
  const scaleRaw = first(raw["scale"]);

  let asOf: string | null = null;
  if (asOfRaw !== undefined && asOfRaw !== "") {
    if (isRealDate(asOfRaw) && asOfRaw >= "2000-01-01" && asOfRaw <= latestCutoff) {
      asOf = asOfRaw === latestCutoff ? null : asOfRaw;
    } else {
      ignored.push("asOf");
    }
  }

  let scale: Scale = "m";
  if (scaleRaw !== undefined && scaleRaw !== "") {
    if (scaleRaw === "m" || scaleRaw === "bn") scale = scaleRaw;
    else ignored.push("scale");
  }
  return { asOf, scale, ignored };
}
