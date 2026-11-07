import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { CompanyDossier, RealCompany, RealIndex } from "@multiverse/contracts";

/*
 * Real companies (Stage 24b, decision D-14), read on the server from `data/companies`: one file per
 * company, written by `python -m multiverse_simulation companies`. A checkout without that folder
 * still works, with the fictional companies only.
 */

const ROOT = join(process.cwd(), "..", "..", "data", "companies");

export interface RealData {
  index: RealIndex;
  byId: ReadonlyMap<string, RealCompany>;
  dossiers: readonly CompanyDossier[];
}

let cached: RealData | null = null;

function load(): RealData | null {
  const indexPath = join(ROOT, "index.json");
  if (!existsSync(indexPath)) return null;
  const index = JSON.parse(readFileSync(indexPath, "utf8")) as RealIndex;
  const records = index.companies.map(
    (row) => JSON.parse(readFileSync(join(ROOT, `${row.cik}.json`), "utf8")) as RealCompany,
  );
  return {
    index,
    byId: new Map(records.map((record) => [record.dossier.company.company_id, record])),
    dossiers: records.map((record) => record.dossier),
  };
}

export function realData(): RealData | null {
  cached ??= load();
  return cached;
}

export function realCompany(companyId: string): RealCompany | null {
  return realData()?.byId.get(companyId) ?? null;
}
