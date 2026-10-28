import type { CompanyDossier } from "@multiverse/contracts";
import { DEMO_DOSSIERS } from "@multiverse/contracts/demo";
import type { CoverageFilter, ExplorerQuery } from "@/companies/params";
import type { CompanyHit, CompanyRepository } from "@/companies/repository";
import { compareMatches, currentName, matchCompany } from "@/companies/search";

/** Company repository backed by the synthetic demo fixtures (decision D-01). */

function revenueQuarters(dossier: CompanyDossier): number {
  return dossier.coverage.find((entry) => entry.metric === "revenue")?.quarters_valid ?? 0;
}

function passesCoverage(dossier: CompanyDossier, filter: CoverageFilter | null): boolean {
  if (filter === null) return true;
  const quarters = revenueQuarters(dossier);
  if (filter === "12-plus") return quarters >= 12;
  if (filter === "8-plus") return quarters >= 8;
  return quarters < 8;
}

export function createFixtureRepository(
  dossiers: readonly CompanyDossier[] = DEMO_DOSSIERS,
): CompanyRepository {
  const byId = new Map(dossiers.map((dossier) => [dossier.company.company_id, dossier]));

  return {
    dataOrigin: "synthetic",

    async search(query: ExplorerQuery) {
      const hits: CompanyHit[] = [];
      for (const dossier of dossiers) {
        const { company } = dossier;
        if (query.sector && company.sector !== query.sector) continue;
        if (query.country && company.country !== query.country) continue;
        if (query.status && company.status !== query.status) continue;
        if (!passesCoverage(dossier, query.coverage)) continue;
        const match = matchCompany(company, query.q);
        if (query.q !== "" && match === null) continue;
        hits.push({
          company,
          supportStatus: dossier.support_status,
          revenueCoverage: dossier.coverage.find((entry) => entry.metric === "revenue") ?? null,
          match,
        });
      }
      return hits.sort(
        (a, b) =>
          compareMatches(a.match, b.match) ||
          currentName(a.company).name.localeCompare(currentName(b.company).name),
      );
    },

    async getDossier(companyId: string) {
      return byId.get(companyId) ?? null;
    },

    async facets() {
      const sectors = [...new Set(dossiers.map((d) => d.company.sector))].sort();
      const countries = [...new Set(dossiers.map((d) => d.company.country))].sort();
      return { sectors, countries, total: dossiers.length };
    },

    async listIds() {
      return dossiers.map((dossier) => dossier.company.company_id);
    },
  };
}
