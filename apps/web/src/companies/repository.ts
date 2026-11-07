import type {
  Company,
  CompanyDossier,
  CoverageEntry,
  DataOrigin,
  RankEvidence,
  Sector,
  SupportStatus,
} from "@multiverse/contracts";
import { DEMO_DOSSIERS } from "@multiverse/contracts/demo";
import { createFixtureRepository } from "@/companies/fixture-repository";
import { realData } from "@/companies/real-data";
import type { ExplorerQuery } from "@/companies/params";
import type { CompanyMatch } from "@/companies/search";

/*
 * Read access to companies (ADR-0012). Pages depend only on this interface, so the
 * fixture implementation can be swapped for the HTTP API adapter in Stages 10-12
 * without touching them. Each method names the endpoint it will call.
 */

export interface CompanyHit {
  company: Company;
  supportStatus: SupportStatus;
  revenueCoverage: CoverageEntry | null;
  match: CompanyMatch | null;
  /** Rank by public float; null for the fictional companies. */
  evidence: RankEvidence | null;
}

export interface CompanyFacets {
  sectors: Sector[];
  countries: string[];
  total: number;
}

export interface CompanyRepository {
  /** Origin of everything this repository returns. */
  readonly dataOrigin: DataOrigin;
  /** GET /api/v1/companies?query=&sector=&country=&status=&coverage= */
  search(query: ExplorerQuery): Promise<readonly CompanyHit[]>;
  /** GET /api/v1/companies/{id}/dossier (identity, coverage, financials, filings, quality). */
  getDossier(companyId: string): Promise<CompanyDossier | null>;
  /** GET /api/v1/companies/facets */
  facets(): Promise<CompanyFacets>;
  /** GET /api/v1/companies?fields=id (static generation of dossier pages). */
  listIds(): Promise<readonly string[]>;
}

let repository: CompanyRepository | undefined;

/** Real companies first, when `data/companies` is there, then the fictional ones. */
export function getCompanyRepository(): CompanyRepository {
  if (repository) return repository;
  const real = realData();
  const evidence = new Map(real?.index.companies.map((row) => [row.company_id, row.evidence]));
  const current = createFixtureRepository([...(real?.dossiers ?? []), ...DEMO_DOSSIERS], evidence);
  repository = current;
  return current;
}
