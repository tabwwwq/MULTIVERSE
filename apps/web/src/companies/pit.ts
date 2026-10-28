import type {
  CompanyDossier,
  CoverageEntry,
  FilingReference,
  MetricValue,
} from "@multiverse/contracts";
import { DOSSIER_METRICS } from "@/companies/labels";

/*
 * Point-in-time view of a dossier (PRD FR-TM-01, ADR-0002). A value counts from the
 * day its filing was published, not from the end of its period: with a cutoff of
 * 2022-06-30, a quarter that ended on 2022-06-30 but was filed in August is
 * "not public yet".
 */

export type CellState = "value" | "missing" | "not_public";

export interface DossierCell {
  metric: string;
  value: MetricValue;
  state: CellState;
  /** Why the value is absent; null when state is "value". */
  reason: string | null;
  filing: FilingReference | null;
}

export interface QuarterRow {
  key: string;
  label: string;
  endDate: string;
  cells: Record<string, DossierCell | undefined>;
}

export interface DossierView {
  /** Effective knowledge cutoff, YYYY-MM-DD. */
  cutoff: string;
  isLatest: boolean;
  rows: QuarterRow[];
  filings: FilingReference[];
  coverage: CoverageEntry[];
  notPublicCount: number;
}

export function dateOnly(isoDateTime: string): string {
  return isoDateTime.slice(0, 10);
}

export function buildDossierView(dossier: CompanyDossier, asOf: string | null): DossierView {
  const latest = dateOnly(dossier.as_of);
  const cutoff = asOf ?? latest;
  const cutoffInstant = asOf ? `${asOf}T23:59:59Z` : dossier.as_of;
  const isPublic = (filing: FilingReference) =>
    Date.parse(filing.filed_at) <= Date.parse(cutoffInstant);

  const filingsById = new Map(dossier.filings.map((filing) => [filing.filing_id, filing]));
  const rowsByEnd = new Map<string, QuarterRow>();

  // Fiscal-quarter values define the rows; instant values (net debt) join on the period end.
  for (const value of dossier.values) {
    const { period } = value;
    if (period.type !== "fiscal_quarter" || period.end_date > cutoff) continue;
    if (!rowsByEnd.has(period.end_date)) {
      rowsByEnd.set(period.end_date, {
        key: `${period.fiscal_year}-q${period.fiscal_quarter}`,
        label: `FY${period.fiscal_year} Q${period.fiscal_quarter}`,
        endDate: period.end_date,
        cells: {},
      });
    }
  }

  let notPublicCount = 0;
  for (const value of dossier.values) {
    const row = rowsByEnd.get(value.period.end_date);
    if (!row) continue;
    const filing = value.source_ids
      .map((id) => filingsById.get(id))
      .find((candidate): candidate is FilingReference => candidate !== undefined);
    let state: CellState = value.quantity === null ? "missing" : "value";
    let reason = value.missing_reason ?? null;
    if (filing && !isPublic(filing)) {
      state = "not_public";
      reason = `Not public on ${cutoff}: filed on ${dateOnly(filing.filed_at)}.`;
      notPublicCount += 1;
    }
    row.cells[value.metric] = {
      metric: value.metric,
      value,
      state,
      reason,
      filing: filing ?? null,
    };
  }

  const rows = [...rowsByEnd.values()].sort((a, b) => b.endDate.localeCompare(a.endDate));
  const coverage = DOSSIER_METRICS.map(({ slug }) => ({
    metric: slug,
    quarters_valid: rows.filter((row) => row.cells[slug]?.state === "value").length,
    quarters_expected: rows.length,
  }));

  return {
    cutoff,
    isLatest: asOf === null,
    rows,
    filings: dossier.filings.filter(isPublic),
    coverage: rows.length > 0 ? coverage : [],
    notPublicCount,
  };
}

/** Quarter-end dates a user can pick as a cutoff, latest first. */
export function cutoffChoices(dossier: CompanyDossier): string[] {
  const ends = new Set<string>();
  for (const value of dossier.values) {
    if (value.period.type === "fiscal_quarter") ends.add(value.period.end_date);
  }
  return [...ends].sort((a, b) => b.localeCompare(a));
}
