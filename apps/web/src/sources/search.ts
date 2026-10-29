import type { AccessCategory } from "@multiverse/contracts";
import type { DataSource } from "@multiverse/contracts/sources";
import { ACCESS_LABELS, FORMAT_LABELS } from "@/sources/catalog";

/*
 * Catalog search. Every word of the query must appear somewhere in a source: its name,
 * publisher, licence, datasets, identifiers, formats or data dictionary. The result says
 * where each match was found, so a search for a field name leads to its dataset.
 */

export const MAX_CATALOG_QUERY = 80;
const MAX_MATCHES = 5;

export interface SourceHit {
  source: DataSource;
  /** Where the query matched, for example "Field realtime_start in Series observations". */
  matches: string[];
}

interface Entry {
  where: string;
  text: string;
}

function entries(source: DataSource): Entry[] {
  const list: Entry[] = [
    { where: "Name", text: `${source.name} ${source.source_id}` },
    { where: "Publisher", text: `${source.publisher} ${source.region}` },
    { where: "Access", text: ACCESS_LABELS[source.access] },
    { where: "Licence", text: `${source.licence.name} ${source.licence.summary}` },
  ];
  for (const dataset of source.datasets) {
    list.push({
      where: `Dataset ${dataset.title}`,
      text: `${dataset.title} ${dataset.description}`,
    });
    list.push({
      where: `Formats of ${dataset.title}`,
      text: dataset.formats.map((format) => FORMAT_LABELS[format]).join(" "),
    });
    list.push({ where: `Identifiers of ${dataset.title}`, text: dataset.identifiers.join(" ") });
    list.push({ where: `Revisions in ${dataset.title}`, text: dataset.revision_semantics });
    for (const field of dataset.fields) {
      list.push({
        where: `Field ${field.name} in ${dataset.title}`,
        text: `${field.name} ${field.description}`,
      });
    }
  }
  return list;
}

/** Lowercases, collapses whitespace, drops control characters and caps the length. */
export function normalizeCatalogQuery(raw: string): string {
  return raw
    .normalize("NFKC")
    .replace(/\p{Cc}/gu, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_CATALOG_QUERY);
}

export function searchSources(
  sources: readonly DataSource[],
  query: string,
  access: AccessCategory | null,
): SourceHit[] {
  const words = normalizeCatalogQuery(query).toLowerCase().split(" ").filter(Boolean);
  const hits: SourceHit[] = [];
  for (const source of sources) {
    if (access !== null && source.access !== access) continue;
    if (words.length === 0) {
      hits.push({ source, matches: [] });
      continue;
    }
    const list = entries(source).map((entry) => ({ ...entry, lower: entry.text.toLowerCase() }));
    const everyWordFound = words.every((word) => list.some((entry) => entry.lower.includes(word)));
    if (!everyWordFound) continue;
    const matches = list
      .filter((entry) => words.some((word) => entry.lower.includes(word)))
      .map((entry) => entry.where);
    hits.push({ source, matches: [...new Set(matches)].slice(0, MAX_MATCHES) });
  }
  return hits;
}
