import type { CompanyDossier, FilingReference } from "@multiverse/contracts";
import { DOSSIER_METRICS } from "@/companies/labels";
import { buildDossierView, cutoffChoices, dateOnly } from "@/companies/pit";

/*
 * Time Machine (FR-TM-01): what was public about one company at two cutoffs, and what became
 * public in between. A quarter counts from the day its filing was published, never from the
 * end of its period, so each quarter is drawn as the lag between the two.
 */

export type Knowledge = "known_at_first" | "new_in_between" | "not_yet";

export interface QuarterKnowledge {
  key: string;
  label: string;
  endDate: string;
  filedAt: string | null;
  form: string | null;
  knowledge: Knowledge;
}

export interface CellKnowledge {
  value: string | null;
  knowledge: Knowledge | "missing";
}

export interface ComparisonRow {
  key: string;
  label: string;
  endDate: string;
  cells: Record<string, CellKnowledge>;
}

export interface Comparison {
  first: string;
  second: string;
  quarters: QuarterKnowledge[];
  rows: ComparisonRow[];
  knownAtFirst: number;
  newInBetween: number;
  notYet: number;
}

function knowledgeOf(filedAt: string | null, first: string, second: string): Knowledge {
  if (filedAt === null) return "not_yet";
  const day = dateOnly(filedAt);
  if (day <= first) return "known_at_first";
  if (day <= second) return "new_in_between";
  return "not_yet";
}

/**
 * The filing that first made a quarter public: the 10-Q or 10-K of that very period. A value of the
 * dossier points to the latest filing that reported it, often the comparative column a year later.
 */
function firstFiling(dossier: CompanyDossier, endDate: string): FilingReference | null {
  const own = dossier.filings
    .filter((filing) => filing.period_end === endDate)
    .sort((a, b) => a.filed_at.localeCompare(b.filed_at));
  if (own[0]) return own[0];
  const byId = new Map(dossier.filings.map((filing) => [filing.filing_id, filing]));
  const sources = dossier.values
    .filter((value) => value.period.type === "fiscal_quarter" && value.period.end_date === endDate)
    .flatMap((value) => value.source_ids.map((id) => byId.get(id)))
    .filter((filing): filing is FilingReference => filing !== undefined)
    .sort((a, b) => a.filed_at.localeCompare(b.filed_at));
  return sources[0] ?? null;
}

/** Two cutoffs of the company, earlier first, or null when the company has fewer than two. */
export function defaultCutoffs(dossier: CompanyDossier): [string, string] | null {
  const choices = cutoffChoices(dossier);
  if (choices.length < 2) return null;
  const second = choices[0] as string;
  const first = choices[Math.min(4, choices.length - 1)] as string;
  return [first, second];
}

export function compareCutoffs(dossier: CompanyDossier, first: string, second: string): Comparison {
  const [early, late] = first <= second ? [first, second] : [second, first];
  const view = buildDossierView(dossier, late);
  const quarters = view.rows
    .map((row) => {
      const filing = firstFiling(dossier, row.endDate);
      return {
        key: row.key,
        label: row.label,
        endDate: row.endDate,
        filedAt: filing ? dateOnly(filing.filed_at) : null,
        form: filing?.form ?? null,
        knowledge: knowledgeOf(filing?.filed_at ?? null, early, late),
      };
    })
    .sort((a, b) => a.endDate.localeCompare(b.endDate));

  const rows = view.rows.map((row) => {
    const cells: Record<string, CellKnowledge> = {};
    for (const metric of DOSSIER_METRICS) {
      const cell = row.cells[metric.slug];
      if (!cell || cell.value.quantity === null) {
        cells[metric.slug] = { value: null, knowledge: "missing" };
        continue;
      }
      cells[metric.slug] = {
        value: cell.value.quantity.value,
        knowledge: knowledgeOf(cell.filing?.filed_at ?? null, early, late),
      };
    }
    return { key: row.key, label: row.label, endDate: row.endDate, cells };
  });

  const count = (state: Knowledge) => quarters.filter((q) => q.knowledge === state).length;
  return {
    first: early,
    second: late,
    quarters,
    rows,
    knownAtFirst: count("known_at_first"),
    newInBetween: count("new_in_between"),
    notYet: count("not_yet"),
  };
}

/** Median days from the end of a quarter to the filing that made it public. */
export function medianLagDays(quarters: readonly QuarterKnowledge[]): number | null {
  const lags = quarters
    .filter((quarter) => quarter.filedAt !== null)
    .map(
      (quarter) =>
        (Date.parse(quarter.filedAt as string) - Date.parse(quarter.endDate)) / 86_400_000,
    )
    .sort((a, b) => a - b);
  if (lags.length === 0) return null;
  const middle = Math.floor(lags.length / 2);
  return Math.round(
    lags.length % 2
      ? (lags[middle] as number)
      : ((lags[middle - 1] as number) + (lags[middle] as number)) / 2,
  );
}
