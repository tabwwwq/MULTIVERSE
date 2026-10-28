import type {
  CompanyDossier,
  CompanyStatus,
  DataOrigin,
  Sector,
  SupportStatus,
} from "@multiverse/contracts";
import { buildDossierView, cutoffChoices, dateOnly, type QuarterRow } from "@/companies/pit";
import { currentListing, currentName } from "@/companies/search";
import { add, toDecimalString } from "@/lib/decimal";

/*
 * What a decision needs to know about its company at each possible knowledge cutoff,
 * computed on the server from the point-in-time dossier view. Only values filed by the
 * cutoff count (ADR-0002), so the same decision resolves to different dollars at
 * different cutoffs. That is why a result goes stale when the cutoff changes.
 */

export interface BaseFigure {
  /** Trailing four quarters (flows) or the latest value (net debt); null when unknown. */
  value: string | null;
  /** Why the value is unknown; null when it is known. */
  reason: string | null;
  /** Quarters behind the value, latest first, e.g. "FY2022 Q3". */
  quarters: string[];
  /** Latest filing date among those quarters, YYYY-MM-DD. */
  lastFiled: string | null;
}

export interface CutoffFacts {
  asOf: string;
  /** Quarters with a public revenue value: PRD FC-02 needs at least 8. */
  quartersPublic: number;
  revenue: BaseFigure;
  rnd: BaseFigure;
  netDebt: BaseFigure;
}

export interface CompanyContext {
  companyId: string;
  name: string;
  ticker: string | null;
  sector: Sector;
  dataOrigin: DataOrigin;
  supportStatus: SupportStatus;
  supportReason: string | null;
  status: CompanyStatus;
  statusDate: string | null;
  statusNote: string | null;
  /** First filing the company ever published, YYYY-MM-DD (PRD FC-03). */
  firstFiled: string | null;
  /** One entry per selectable cutoff, latest first. */
  cutoffs: CutoffFacts[];
}

export const MIN_QUARTERS = 8;

function trailingFour(
  rows: readonly QuarterRow[],
  metric: string,
  label: string,
  cutoff: string,
): BaseFigure {
  const known = rows.filter(
    (row) => row.cells[metric] && row.cells[metric]?.state !== "not_public",
  );
  const window = known.slice(0, 4);
  const quarters = window.map((row) => row.label);
  const lastFiled =
    window
      .map((row) => row.cells[metric]?.filing?.filed_at)
      .filter((filed): filed is string => filed !== undefined)
      .map(dateOnly)
      .sort()
      .at(-1) ?? null;
  if (window.length < 4) {
    return {
      value: null,
      reason: `Only ${window.length} quarter${window.length === 1 ? "" : "s"} of ${label} were public by ${cutoff}; four are needed.`,
      quarters,
      lastFiled,
    };
  }
  let total = "0";
  for (const row of window) {
    const cell = row.cells[metric];
    const quantity = cell?.value.quantity;
    if (!cell || cell.state !== "value" || !quantity) {
      return {
        value: null,
        reason: `${label} for ${row.label} is missing: ${cell?.reason ?? "no value"}`,
        quarters,
        lastFiled,
      };
    }
    total = toDecimalString(add(total, quantity.value));
  }
  return { value: total, reason: null, quarters, lastFiled };
}

function latest(
  rows: readonly QuarterRow[],
  metric: string,
  label: string,
  cutoff: string,
): BaseFigure {
  const row = rows.find((candidate) => candidate.cells[metric]?.state === "value");
  const cell = row?.cells[metric];
  if (!row || !cell?.value.quantity) {
    return {
      value: null,
      reason: `No ${label} was public by ${cutoff}.`,
      quarters: [],
      lastFiled: null,
    };
  }
  return {
    value: cell.value.quantity.value,
    reason: null,
    quarters: [row.label],
    lastFiled: cell.filing ? dateOnly(cell.filing.filed_at) : null,
  };
}

export function factsAt(dossier: CompanyDossier, cutoff: string): CutoffFacts {
  const view = buildDossierView(dossier, cutoff);
  return {
    asOf: cutoff,
    quartersPublic: view.rows.filter((row) => row.cells["revenue"]?.state === "value").length,
    revenue: trailingFour(view.rows, "revenue", "revenue", cutoff),
    rnd: trailingFour(view.rows, "rnd_expense", "R&D expense", cutoff),
    netDebt: latest(view.rows, "net_debt", "net debt", cutoff),
  };
}

export function buildCompanyContext(dossier: CompanyDossier): CompanyContext {
  const { company } = dossier;
  const firstFiled = dossier.filings.map((filing) => dateOnly(filing.filed_at)).sort()[0] ?? null;
  return {
    companyId: company.company_id,
    name: currentName(company).name,
    ticker: currentListing(company)?.ticker ?? null,
    sector: company.sector,
    dataOrigin: company.data_origin,
    supportStatus: dossier.support_status,
    supportReason: dossier.support_reason,
    status: company.status,
    statusDate: company.status_date,
    statusNote: company.status_note,
    firstFiled,
    cutoffs: cutoffChoices(dossier).map((cutoff) => factsAt(dossier, cutoff)),
  };
}
