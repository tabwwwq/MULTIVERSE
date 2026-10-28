import type { ScenarioResult } from "@multiverse/contracts";
import { MOCK_RESULTS } from "@multiverse/contracts/mock-results";

/*
 * Read access to scenario results, like CompanyRepository (ADR-0012). Pages depend on
 * this interface only; the mock implementation is replaced by the API adapter when the
 * Monte Carlo engine exists (Stage 22). Each method names the endpoint it will call.
 */

export interface ResultSummary {
  resultId: string;
  title: string;
  companyName: string;
  asOf: string;
  status: ScenarioResult["status"];
  scenarios: string[];
  mock: boolean;
}

export interface ResultRepository {
  /** GET /api/v1/simulations */
  list(): Promise<readonly ResultSummary[]>;
  /** GET /api/v1/simulations/{id} with /metrics (quantiles, changes, distributions). */
  get(resultId: string): Promise<ScenarioResult | null>;
  /** GET /api/v1/simulations?fields=id (static generation). */
  listIds(): Promise<readonly string[]>;
}

export function summarize(result: ScenarioResult): ResultSummary {
  return {
    resultId: result.result_id,
    title: result.title,
    companyName: result.company_name,
    asOf: result.as_of,
    status: result.status,
    scenarios: result.scenarios.map((run) => run.label),
    mock: result.mock,
  };
}

export function createMockResultRepository(
  results: readonly ScenarioResult[] = MOCK_RESULTS,
): ResultRepository {
  const byId = new Map(results.map((result) => [result.result_id, result]));
  return {
    async list() {
      return results.map(summarize);
    },
    async get(resultId) {
      return byId.get(resultId) ?? null;
    },
    async listIds() {
      return results.map((result) => result.result_id);
    },
  };
}

let repository: ResultRepository | undefined;

export function getResultRepository(): ResultRepository {
  const current = repository ?? createMockResultRepository();
  repository = current;
  return current;
}
