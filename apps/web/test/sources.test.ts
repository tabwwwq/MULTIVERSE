import { describe, expect, it } from "vitest";
import { safeExternalUrl } from "@/lib/safe-url";
import { MAX_SCORE, SOURCE_CATALOG, SOURCES, sourceById } from "@/sources/catalog";
import { parseCatalogParams } from "@/sources/params";
import { MAX_CATALOG_QUERY, normalizeCatalogQuery, searchSources } from "@/sources/search";

const ids = (query: string, access: Parameters<typeof searchSources>[2] = null) =>
  searchSources(SOURCES, query, access).map((hit) => hit.source.source_id);

describe("source catalog", () => {
  it("holds metadata only, with every download awaiting the owner", () => {
    expect(SOURCE_CATALOG.automatic_downloads).toBe("disabled");
    for (const source of SOURCES) {
      expect(source.download.status, source.source_id).toBe("awaiting_owner_decision");
    }
  });

  it("links every document through the official-host allowlist", () => {
    for (const source of SOURCES) {
      const docs = [...source.docs, ...source.datasets.flatMap((dataset) => dataset.docs)];
      for (const doc of docs) expect(safeExternalUrl(doc.url), doc.url).toBe(doc.url);
    }
  });

  it("scores candidates out of the rubric maximum", () => {
    expect(MAX_SCORE).toBe(26);
    for (const candidate of SOURCE_CATALOG.candidates) {
      expect(candidate.total).toBeLessThanOrEqual(MAX_SCORE);
    }
  });

  it("finds a source by its ID", () => {
    expect(sourceById("fred-alfred")?.access).toBe("api_key");
    expect(sourceById("bloomberg")).toBeUndefined();
  });
});

describe("catalog search", () => {
  it("returns every source for an empty query", () => {
    expect(ids("")).toEqual(["sec-edgar", "fred-alfred", "ecb-data-portal", "world-bank"]);
  });

  it("finds a field name and says where it matched", () => {
    const hits = searchSources(SOURCES, "realtime_start", null);
    expect(hits.map((hit) => hit.source.source_id)).toEqual(["fred-alfred"]);
    expect(hits[0]?.matches).toContain("Field realtime_start in Series observations with vintages");
  });

  it("needs every word to match somewhere in the same source", () => {
    expect(ids("cik accession")).toEqual(["sec-edgar"]);
    expect(ids("cik sdmx")).toEqual([]);
  });

  it("searches revision rules, so vintages lead to the sources that keep them", () => {
    const found = ids("vintage");
    expect(found).toContain("fred-alfred");
    expect(found).toContain("world-bank");
    expect(found).not.toContain("ecb-data-portal");
  });

  it("filters by access category", () => {
    expect(ids("", "api_key")).toEqual(["fred-alfred"]);
    expect(ids("", "licensed")).toEqual([]);
  });

  it("normalizes the query", () => {
    expect(normalizeCatalogQuery("  CIK\u0007   number ")).toBe("CIK number");
    expect(normalizeCatalogQuery("x".repeat(200))).toHaveLength(MAX_CATALOG_QUERY);
  });
});

describe("catalog URL parameters", () => {
  it("accepts allowlisted values", () => {
    expect(parseCatalogParams({ q: "fred", access: "api_key" })).toEqual({
      query: { q: "fred", access: "api_key" },
      ignored: [],
      shortened: false,
    });
  });

  it("drops an unknown access type and reports it by name only", () => {
    const parsed = parseCatalogParams({ access: "<script>" });
    expect(parsed.query.access).toBeNull();
    expect(parsed.ignored).toEqual(["access"]);
  });

  it("takes the first value of repeated parameters and flags long text", () => {
    const parsed = parseCatalogParams({ q: ["sec", "fred"], access: ["licensed"] });
    expect(parsed.query).toEqual({ q: "sec", access: "licensed" });
    expect(parseCatalogParams({ q: "a".repeat(100) }).shortened).toBe(true);
  });
});
