import type { DecisionType } from "@multiverse/contracts/interventions";
import type { RawParams } from "@/companies/params";
import { isDecisionType } from "@/decisions/catalog";

/*
 * Link parameters of the Decision Builder, checked against an allowlist like the
 * explorer's (Stage 04 safe URL rules): rejected values are reported by parameter
 * name only, never echoed.
 */

export interface ParsedDecisionParams {
  companyId: string | null;
  asOf: string | null;
  type: DecisionType;
  ignored: string[];
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function parseDecisionParams(
  raw: RawParams,
  knownCompanies: readonly string[],
  cutoffsOf: (companyId: string) => readonly string[],
): ParsedDecisionParams {
  const ignored: string[] = [];
  const company = first(raw["company"]);
  const asOf = first(raw["asOf"]);
  const type = first(raw["type"]);

  let companyId: string | null = null;
  if (company !== undefined && company !== "") {
    if (knownCompanies.includes(company)) companyId = company;
    else ignored.push("company");
  }
  let cutoff: string | null = null;
  if (asOf !== undefined && asOf !== "") {
    if (companyId !== null && cutoffsOf(companyId).includes(asOf)) cutoff = asOf;
    else ignored.push("asOf");
  }
  let decisionType: DecisionType = "rnd_change";
  if (type !== undefined && type !== "") {
    if (isDecisionType(type)) decisionType = type;
    else ignored.push("type");
  }
  return { companyId, asOf: cutoff, type: decisionType, ignored };
}

export function decisionsHref(
  companyId: string,
  asOf?: string | null,
  type?: DecisionType,
): string {
  const params = new URLSearchParams({ company: companyId });
  if (asOf) params.set("asOf", asOf);
  if (type) params.set("type", type);
  return `/decisions?${params.toString()}`;
}
