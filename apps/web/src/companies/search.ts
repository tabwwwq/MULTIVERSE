import type { Company, DatedName, TickerListing } from "@multiverse/contracts";

/*
 * Company search. Tickers and names are histories, so former tickers and former
 * names match too, and the result says which one matched (PRD FR-CO-01, US-01).
 */

export const MAX_QUERY_LENGTH = 64;

export type MatchField = "cik" | "ticker" | "former_ticker" | "name" | "former_name";

export interface CompanyMatch {
  field: MatchField;
  value: string;
  /** Last day the matched ticker or name was used; null while it is current. */
  until: string | null;
}

const PRIORITY: Record<MatchField, number> = {
  cik: 0,
  ticker: 1,
  former_ticker: 2,
  name: 3,
  former_name: 4,
};

/** Trims, collapses whitespace, drops control characters and caps the length. */
export function normalizeQuery(raw: string): string {
  return raw
    .normalize("NFKC")
    .replace(/\p{Cc}/gu, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_QUERY_LENGTH);
}

function lastOf<T>(items: readonly T[]): T | undefined {
  return items[items.length - 1];
}

export function currentName(company: Company): DatedName {
  return lastOf(company.names) ?? company.names[0];
}

export function currentListing(company: Company): TickerListing | undefined {
  return lastOf(company.listings);
}

export function formerListings(company: Company): TickerListing[] {
  return company.listings.slice(0, -1);
}

export function matchCompany(company: Company, query: string): CompanyMatch | null {
  if (query === "") return null;
  const upper = query.toUpperCase();
  const lower = query.toLowerCase();

  if (/^\d{1,10}$/.test(query) && company.cik) {
    if (company.cik.replace(/^0+/, "") === query.replace(/^0+/, "")) {
      return { field: "cik", value: company.cik, until: null };
    }
  }

  const listing = currentListing(company);
  if (listing?.ticker === upper) {
    return { field: "ticker", value: listing.ticker, until: listing.valid_to ?? null };
  }
  for (const former of formerListings(company)) {
    if (former.ticker === upper) {
      return { field: "former_ticker", value: former.ticker, until: former.valid_to ?? null };
    }
  }
  if (listing && listing.ticker.startsWith(upper)) {
    return { field: "ticker", value: listing.ticker, until: listing.valid_to ?? null };
  }

  const name = currentName(company);
  if (name.name.toLowerCase().includes(lower)) {
    return { field: "name", value: name.name, until: null };
  }
  for (const former of company.names.slice(0, -1)) {
    if (former.name.toLowerCase().includes(lower)) {
      return { field: "former_name", value: former.name, until: former.valid_to ?? null };
    }
  }
  return null;
}

export function compareMatches(a: CompanyMatch | null, b: CompanyMatch | null): number {
  return (a ? PRIORITY[a.field] : 99) - (b ? PRIORITY[b.field] : 99);
}
