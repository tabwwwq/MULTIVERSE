import { DEMO_DOSSIERS } from "@multiverse/contracts/demo";
import { describe, expect, it } from "vitest";
import { createFixtureRepository } from "@/companies/fixture-repository";
import { formatAmount } from "@/companies/format";
import { parseDossierParams, parseExplorerParams } from "@/companies/params";
import { buildDossierView, cutoffChoices } from "@/companies/pit";
import { matchCompany, normalizeQuery } from "@/companies/search";
import { safeExternalUrl } from "@/lib/safe-url";

function dossier(ticker: string) {
  const found = DEMO_DOSSIERS.find((d) => d.company.listings.at(-1)?.ticker === ticker);
  if (!found) throw new Error(`no demo company ${ticker}`);
  return found;
}

const northwind = dossier("NWSC");
const repository = createFixtureRepository();
const emptyQuery = { q: "", sector: null, country: null, status: null, coverage: null };

describe("search matching", () => {
  it("finds a company by its former ticker and says until when it was used", () => {
    expect(matchCompany(northwind.company, "nwmd")).toEqual({
      field: "former_ticker",
      value: "NWMD",
      until: "2019-06-30",
    });
  });

  it("matches a CIK with or without leading zeros", () => {
    expect(matchCompany(northwind.company, "99000101")?.field).toBe("cik");
    expect(matchCompany(northwind.company, "0099000101")?.field).toBe("cik");
  });

  it("matches current and former names case-insensitively", () => {
    expect(matchCompany(northwind.company, "semiconductors")?.field).toBe("name");
    expect(matchCompany(northwind.company, "MICRODEVICES")?.field).toBe("former_name");
  });

  it("returns no match for unrelated text", () => {
    expect(matchCompany(northwind.company, "AAPL")).toBeNull();
  });

  it("normalizes queries: whitespace, control characters and length", () => {
    expect(normalizeQuery("  north\u0000  wind  ")).toBe("north wind");
    expect(normalizeQuery("x".repeat(200))).toHaveLength(64);
  });
});

describe("fixture repository", () => {
  it("lists all seven synthetic companies for an empty query", async () => {
    expect(await repository.search(emptyQuery)).toHaveLength(7);
    expect(repository.dataOrigin).toBe("synthetic");
  });

  it("returns nothing for a real ticker that is not in the demo universe", async () => {
    expect(await repository.search({ ...emptyQuery, q: "AAPL" })).toEqual([]);
  });

  it("filters by lifecycle, sector and coverage", async () => {
    const acquired = await repository.search({ ...emptyQuery, status: "acquired" });
    expect(acquired.map((hit) => hit.company.listings.at(-1)?.ticker)).toEqual(["AGRU"]);

    const software = await repository.search({ ...emptyQuery, sector: "software" });
    expect(software).toHaveLength(1);

    const short = await repository.search({ ...emptyQuery, coverage: "under-8" });
    expect(short.map((hit) => hit.company.listings.at(-1)?.ticker).sort()).toEqual([
      "TSLG",
      "VLTX",
    ]);
  });

  it("returns null for an unknown company id", async () => {
    expect(await repository.getDossier("00000000-0000-4000-8000-000000000000")).toBeNull();
  });
});

describe("URL parameters", () => {
  it("accepts allowlisted explorer filters", () => {
    const parsed = parseExplorerParams({
      q: "nw",
      sector: "software",
      status: "active",
      coverage: "8-plus",
    });
    expect(parsed.query).toEqual({
      q: "nw",
      sector: "software",
      country: null,
      status: "active",
      coverage: "8-plus",
    });
    expect(parsed.ignored).toEqual([]);
  });

  it("drops invalid values and reports only the parameter names", () => {
    const parsed = parseExplorerParams({
      sector: "<script>alert(1)</script>",
      country: "Germany",
      status: "zombie",
      unknown: "anything",
    });
    expect(parsed.query.sector).toBeNull();
    expect(parsed.ignored).toEqual(["sector", "country", "status"]);
  });

  it("shortens very long search text and says so", () => {
    const parsed = parseExplorerParams({ q: "a".repeat(500) });
    expect(parsed.query.q).toHaveLength(64);
    expect(parsed.shortened).toBe(true);
  });

  it("accepts a cutoff inside the snapshot and rejects future or malformed dates", () => {
    expect(parseDossierParams({ asOf: "2022-06-30" }, "2023-03-31").asOf).toBe("2022-06-30");
    expect(parseDossierParams({ asOf: "2099-01-01" }, "2023-03-31").ignored).toEqual(["asOf"]);
    expect(parseDossierParams({ asOf: "2022-02-30" }, "2023-03-31").ignored).toEqual(["asOf"]);
    expect(parseDossierParams({ scale: "trillion" }, "2023-03-31")).toEqual({
      asOf: null,
      scale: "m",
      ignored: ["scale"],
    });
  });
});

describe("point-in-time view", () => {
  it("shows every quarter of the snapshot by default, latest first", () => {
    const view = buildDossierView(northwind, null);
    expect(view.rows).toHaveLength(12);
    expect(view.rows[0]?.label).toBe("FY2022 Q4");
    expect(view.notPublicCount).toBe(0);
  });

  it("marks a quarter that ended before the cutoff but was filed after it as not public", () => {
    const view = buildDossierView(northwind, "2022-06-30");
    const latest = view.rows[0];
    expect(latest?.label).toBe("FY2022 Q2");
    expect(latest?.cells["revenue"]?.state).toBe("not_public");
    expect(latest?.cells["revenue"]?.reason).toMatch(
      /^Not public on 2022-06-30: filed on 2022-08-/,
    );
    expect(view.rows[1]?.cells["revenue"]?.state).toBe("value");
  });

  it("keeps a missing value missing, with its reason, never zero", () => {
    const row = buildDossierView(northwind, null).rows.find((r) => r.label === "FY2021 Q3");
    expect(row?.cells["rnd_expense"]?.state).toBe("missing");
    expect(row?.cells["rnd_expense"]?.reason).toMatch(/not tagged separately/);
  });

  it("recomputes coverage for the chosen cutoff", () => {
    const coverage = buildDossierView(northwind, "2022-06-30").coverage.find(
      (c) => c.metric === "revenue",
    );
    expect(coverage).toEqual({ metric: "revenue", quarters_valid: 9, quarters_expected: 10 });
  });

  it("offers quarter ends as cutoffs", () => {
    expect(cutoffChoices(northwind)[0]).toBe("2022-12-31");
  });

  it("keeps the values before a reporting currency change missing instead of converting them", () => {
    const kestrel = buildDossierView(dossier("KSTL"), null);
    const fy2020 = kestrel.rows.filter((row) => row.label.startsWith("FY2020"));
    expect(fy2020).toHaveLength(4);
    for (const row of fy2020) {
      expect(row.cells["revenue"]?.state).toBe("missing");
      expect(row.cells["revenue"]?.reason).toMatch(/CAD/);
    }
  });
});

describe("formatting", () => {
  it("formats amounts in millions or billions with a true minus sign", () => {
    expect(formatAmount("1204300000", "m")).toBe("1,204");
    expect(formatAmount("1204300000", "bn")).toBe("1.20");
    expect(formatAmount("-450000000", "m")).toBe("−450");
  });
});

describe("safe external URLs", () => {
  it("allows official sources over HTTPS", () => {
    expect(safeExternalUrl("https://www.sec.gov/cgi-bin/browse-edgar?CIK=1")).toBe(
      "https://www.sec.gov/cgi-bin/browse-edgar?CIK=1",
    );
  });

  it.each([
    ["javascript scheme", "javascript:alert(1)"],
    ["plain HTTP", "http://www.sec.gov/"],
    ["lookalike host", "https://www.sec.gov.example.com/"],
    ["credentials", "https://user@www.sec.gov/"],
    ["custom port", "https://www.sec.gov:8443/"],
    ["unlisted host", "https://example.com/"],
    ["not a URL", "sec.gov"],
  ])("rejects %s", (_name, url) => {
    expect(safeExternalUrl(url)).toBeNull();
  });
});
