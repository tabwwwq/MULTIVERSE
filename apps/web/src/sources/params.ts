import type { AccessCategory } from "@multiverse/contracts";
import { ACCESS_ORDER } from "@/sources/catalog";
import { MAX_CATALOG_QUERY, normalizeCatalogQuery } from "@/sources/search";

/*
 * Safe URL handling for the Data Catalog, with the same rules as the Universe Explorer:
 * allowlisted values only, invalid ones dropped and reported by parameter name, the raw
 * value never echoed back.
 */

export type RawParams = Record<string, string | string[] | undefined>;

export interface CatalogQuery {
  q: string;
  access: AccessCategory | null;
}

export interface ParsedCatalogParams {
  query: CatalogQuery;
  ignored: string[];
  shortened: boolean;
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function parseCatalogParams(raw: RawParams): ParsedCatalogParams {
  const rawQuery = first(raw["q"]) ?? "";
  const rawAccess = first(raw["access"]);
  const access =
    rawAccess !== undefined && (ACCESS_ORDER as readonly string[]).includes(rawAccess)
      ? (rawAccess as AccessCategory)
      : null;
  const ignored = rawAccess !== undefined && rawAccess !== "" && access === null ? ["access"] : [];
  return {
    query: { q: normalizeCatalogQuery(rawQuery), access },
    ignored,
    shortened: rawQuery.trim().length > MAX_CATALOG_QUERY,
  };
}
