import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { SECTIONS } from "../src/navigation/sections";

const PAGES = [
  { path: "/", name: "overview", heading: "What if business took another path?" },
  { path: "/methodology", name: "methodology", heading: "Methodology" },
  { path: "/design-system", name: "design-system", heading: "Design system" },
  { path: "/time-machine", name: "planned-section", heading: "Time Machine" },
  { path: "/universe", name: "explorer", heading: "Universe Explorer" },
  {
    path: "/dossier/5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13",
    name: "dossier",
    heading: "Northwind Semiconductors Inc.",
  },
  {
    path: "/dossier/8d2c6e1a-4f9b-4b70-8e3d-c5a1f7b2e906",
    name: "dossier-unsupported",
    heading: "Valtrix AG",
  },
] as const;

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const SCREENS_DIR = fileURLToPath(
  new URL(`../../../docs/stages/${process.env["SAVE_SCREENS"] ?? "screens"}/`, import.meta.url),
);

for (const target of PAGES) {
  test.describe(`page ${target.path}`, () => {
    test("renders its heading without horizontal overflow", async ({ page }, testInfo) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto(target.path);
      await expect(page.getByRole("heading", { level: 1, name: target.heading })).toBeVisible();

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, "horizontal overflow in px").toBeLessThanOrEqual(0);

      await testInfo.attach("full page", {
        body: await page.screenshot({ fullPage: true }),
        contentType: "image/png",
      });
      if (process.env["SAVE_SCREENS"]) {
        mkdirSync(SCREENS_DIR, { recursive: true });
        await page.screenshot({
          path: `${SCREENS_DIR}${target.name}-${testInfo.project.name}.png`,
        });
      }
    });

    test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto(target.path);
      const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
      const violations = results.violations.map(
        (violation) =>
          `${violation.id} (${violation.impact}): ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`,
      );
      expect(violations).toEqual([]);
    });
  });
}

test("every planned section shows an honest placeholder without data", async ({ page }) => {
  const planned = SECTIONS.filter((section) => section.status === "planned");
  expect(planned.length).toBe(16);
  for (const section of planned) {
    const response = await page.goto(section.href);
    expect(response?.status(), section.href).toBe(200);
    await expect(page.getByRole("heading", { level: 1, name: section.title })).toBeVisible();
    await expect(page.getByRole("main").getByText("Not built yet", { exact: true })).toBeVisible();
    await expect(page.locator("main table, main input, main select")).toHaveCount(0);
  }
});

test("unknown paths answer 404 with a way back", async ({ page }) => {
  const response = await page.goto("/does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(
    page.getByRole("heading", { level: 1, name: "This page does not exist" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to the overview" })).toHaveAttribute("href", "/");
});

test("no internal link is broken", async ({ page, request }) => {
  const hrefs = new Set<string>();
  for (const target of PAGES) {
    await page.goto(target.path);
    const found = await page
      .locator('a[href^="/"]')
      .evaluateAll((links) => links.map((link) => link.getAttribute("href") ?? ""));
    for (const href of found) hrefs.add(href.split("#")[0] || "/");
  }
  for (const href of hrefs) {
    const response = await request.get(href);
    expect(response.status(), href).toBe(200);
  }
});
