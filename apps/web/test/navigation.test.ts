import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildBreadcrumbs } from "@/navigation/breadcrumbs";
import { NAV_GROUPS, SECTIONS, formatStage } from "@/navigation/sections";

const APP_DIR = fileURLToPath(new URL("../src/app", import.meta.url));

describe("sections", () => {
  it("cover the 20 screens of the information architecture", () => {
    expect(SECTIONS).toHaveLength(20);
  });

  it("have unique paths and slugs", () => {
    expect(new Set(SECTIONS.map((section) => section.href)).size).toBe(SECTIONS.length);
    expect(new Set(SECTIONS.map((section) => section.slug)).size).toBe(SECTIONS.length);
  });

  it("belong to a known navigation group, and every group is used", () => {
    const groupIds = new Set(NAV_GROUPS.map((group) => group.id));
    for (const section of SECTIONS) expect(groupIds).toContain(section.group);
    for (const group of NAV_GROUPS)
      expect(SECTIONS.some((section) => section.group === group.id)).toBe(true);
  });

  it("only mark a section available when its page exists", () => {
    for (const section of SECTIONS.filter((candidate) => candidate.status === "available")) {
      const page = section.slug === "" ? "page.tsx" : `${section.slug}/page.tsx`;
      expect(existsSync(`${APP_DIR}/${page}`), `${section.title} needs src/app/${page}`).toBe(true);
    }
  });

  it("describe what every planned section will do and name a later stage", () => {
    for (const section of SECTIONS.filter((candidate) => candidate.status === "planned")) {
      expect(section.plans.length, section.title).toBeGreaterThan(0);
      expect(section.stage, section.title).toBeGreaterThan(3);
    }
  });

  it("do not give planned sections their own page files, which would bypass the placeholder", () => {
    for (const section of SECTIONS.filter((candidate) => candidate.status === "planned")) {
      expect(existsSync(`${APP_DIR}/${section.slug}/page.tsx`), section.title).toBe(false);
    }
  });

  it("format stages with two digits", () => {
    expect(formatStage(5)).toBe("Stage 05");
    expect(formatStage(23)).toBe("Stage 23");
  });
});

describe("breadcrumbs", () => {
  it("show only the overview on the home page", () => {
    expect(buildBreadcrumbs("/")).toEqual([{ label: "Overview" }]);
  });

  it("show overview, group and page for a section", () => {
    expect(buildBreadcrumbs("/universe")).toEqual([
      { label: "Overview", href: "/" },
      { label: "Explore" },
      { label: "Universe Explorer" },
    ]);
  });

  it("skip the group for overview pages and tolerate a trailing slash", () => {
    expect(buildBreadcrumbs("/methodology/")).toEqual([
      { label: "Overview", href: "/" },
      { label: "Methodology" },
    ]);
  });

  it("include pages outside the information architecture", () => {
    expect(buildBreadcrumbs("/design-system")).toEqual([
      { label: "Overview", href: "/" },
      { label: "Design system" },
    ]);
  });

  it("link back to the section from a nested page", () => {
    expect(buildBreadcrumbs("/dossier/5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13")).toEqual([
      { label: "Overview", href: "/" },
      { label: "Explore" },
      { label: "Company Dossier", href: "/dossier" },
      { label: "Company profile" },
    ]);
  });

  it("name a single result under its section", () => {
    expect(buildBreadcrumbs("/timeline/2d7c9e41-5b3a-4f6e-8c1d-9a0b7e6f5c34").at(-1)).toEqual({
      label: "Result",
    });
  });

  it("fall back to the overview for unknown paths", () => {
    expect(buildBreadcrumbs("/nope")).toEqual([{ label: "Overview", href: "/" }]);
  });
});
