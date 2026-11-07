import type { CompanyDossier } from "@multiverse/contracts";
import { DEMO_DOSSIERS } from "@multiverse/contracts/demo";
import { describe, expect, it } from "vitest";
import { cutoffChoices } from "@/companies/pit";
import { compareCutoffs, defaultCutoffs, medianLagDays } from "@/time-machine/compare";

const dossier = DEMO_DOSSIERS.find((item) => cutoffChoices(item).length >= 6) as CompanyDossier;

describe("Time Machine", () => {
  it("puts every quarter in exactly one state, by the day its filing was published", () => {
    const [first, second] = defaultCutoffs(dossier) as [string, string];
    const found = compareCutoffs(dossier, first, second);
    expect(found.first < found.second).toBe(true);
    expect(found.knownAtFirst + found.newInBetween + found.notYet).toBe(found.quarters.length);
    for (const quarter of found.quarters) {
      if (quarter.filedAt === null) continue;
      if (quarter.knowledge === "known_at_first") expect(quarter.filedAt <= first).toBe(true);
      if (quarter.knowledge === "new_in_between") {
        expect(quarter.filedAt > first && quarter.filedAt <= second).toBe(true);
      }
      if (quarter.knowledge === "not_yet") expect(quarter.filedAt > second).toBe(true);
      expect(quarter.filedAt >= quarter.endDate).toBe(true);
    }
  });

  it("orders the two dates whichever comes first in the link", () => {
    const [first, second] = defaultCutoffs(dossier) as [string, string];
    expect(compareCutoffs(dossier, second, first)).toEqual(compareCutoffs(dossier, first, second));
  });

  it("takes the first filing of a quarter, not a later comparative column", () => {
    const [first, second] = defaultCutoffs(dossier) as [string, string];
    const found = compareCutoffs(dossier, first, second);
    for (const quarter of found.quarters) {
      const own = dossier.filings
        .filter((filing) => filing.period_end === quarter.endDate)
        .map((filing) => filing.filed_at.slice(0, 10))
        .sort();
      if (own[0]) expect(quarter.filedAt).toBe(own[0]);
    }
  });

  it("shows only quarters that ended by the second date", () => {
    const choices = cutoffChoices(dossier);
    const found = compareCutoffs(dossier, choices[5] as string, choices[3] as string);
    expect(found.rows.every((row) => row.endDate <= (choices[3] as string))).toBe(true);
  });

  it("measures the median lag between a quarter and its filing", () => {
    const quarters = [
      {
        key: "a",
        label: "a",
        endDate: "2024-03-31",
        filedAt: "2024-04-30",
        form: "10-Q",
        knowledge: "known_at_first" as const,
      },
      {
        key: "b",
        label: "b",
        endDate: "2024-06-30",
        filedAt: "2024-08-09",
        form: "10-Q",
        knowledge: "known_at_first" as const,
      },
      {
        key: "c",
        label: "c",
        endDate: "2024-09-30",
        filedAt: null,
        form: null,
        knowledge: "not_yet" as const,
      },
    ];
    expect(medianLagDays(quarters)).toBe(35);
    expect(medianLagDays([])).toBeNull();
  });
});
