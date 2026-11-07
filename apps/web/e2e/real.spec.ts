import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

const NVIDIA = "/dossier/f1bad442-6a6f-572e-a9d8-5b4109e7e757";
const BUILDER = "/decisions?company=f1bad442-6a6f-572e-a9d8-5b4109e7e757&type=rnd_change";
const JOB = "job-0123456789ab";
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const REPORT: unknown = JSON.parse(
  readFileSync(
    new URL("../../../data/simulation/report-48898-acquisition.json", import.meta.url),
    "utf8",
  ),
);

function job(status: string, percent: number) {
  return {
    job_id: JOB,
    request: { kind: "simulation" },
    status,
    approved_at: "2026-11-06T10:00:00Z",
    progress_percent: percent,
    elapsed_seconds: 3,
    reason: null,
  };
}

/** The API and the worker of this computer, as far as the screen can tell. */
async function engine(page: Page, posted: string[]) {
  await page.route("**/api/v1/**", (route) => {
    const url = route.request().url();
    if (route.request().method() === "POST") posted.push(url.split("/api/v1")[1] ?? url);
    if (url.endsWith("/simulations/estimate")) {
      return route.fulfill({
        json: { seconds: 5.5, vram_mb: 0, disk_mb: 2.8, cost_usd: 0, basis: "0.0055 s per path" },
      });
    }
    if (url.endsWith("/simulations")) return route.fulfill({ status: 201, json: job("queued", 0) });
    if (url.endsWith("/approve")) return route.fulfill({ json: job("running", 40) });
    if (url.endsWith("/report")) return route.fulfill({ json: REPORT });
    return route.fulfill({ json: { job: job("completed", 100) } });
  });
}

async function checkedDecision(page: Page) {
  await page.goto(BUILDER);
  await page.getByRole("textbox", { name: /^R&D change/ }).fill("20");
  await page
    .getByRole("combobox", { name: /Measured against/ })
    .selectOption({ label: "% of the previous R&D budget" });
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(page.getByTestId("validation-status")).toContainText("No blocking errors");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ready to run" })).toBeVisible();
}

test.describe("Real companies", () => {
  test("puts the largest filer first and says what the rank is", async ({ page }) => {
    await page.goto("/universe");
    await expect(page.getByRole("heading", { level: 3 }).first()).toContainText("NVIDIA");
    await expect(page.locator("main")).toContainText("public float");
    await expect(page.locator("main")).toContainText("not market capitalization");
  });

  test("finds a company by ticker and shows its forecast", async ({ page }) => {
    await page.goto("/universe?q=NVDA");
    await page
      .getByRole("link", { name: /NVIDIA/ })
      .first()
      .click();
    await expect(page).toHaveURL(new RegExp(`${NVIDIA}$`));
    await expect(page.getByText("Research forecast, not approved for the product")).toBeVisible();
    await expect(
      page.getByRole("rowheader", { name: "Revenue growth over a year" }).first(),
    ).toBeVisible();
  });

  test("keeps a fictional company marked as such", async ({ page }) => {
    await page.goto("/universe?q=nwmd");
    await expect(page.getByRole("link", { name: "Northwind Semiconductors Inc." })).toBeVisible();
    await expect(page.getByText(/synthetic/i).first()).toBeVisible();
  });

  test("runs a decision through the queue and opens the result", async ({ page }) => {
    const posted: string[] = [];
    await engine(page, posted);
    await checkedDecision(page);
    await page.getByRole("button", { name: "Run simulation" }).click();
    await expect(page).toHaveURL(new RegExp(`/run\\?job=${JOB}$`));
    await expect(page.getByRole("heading", { level: 1, name: "Simulation result" })).toBeVisible();
    expect(posted).toEqual(["/simulations/estimate", "/simulations", `/jobs/${JOB}/approve`]);
  });

  test("says how to start the engine when it is off", async ({ page }) => {
    await page.route("**/api/v1/**", (route) => route.abort());
    await checkedDecision(page);
    await page.getByRole("button", { name: "Run simulation" }).click();
    await expect(page.getByText("The engine is not running on this computer")).toBeVisible();
    await expect(page.getByRole("dialog").getByText("npm run app")).toBeVisible();
  });

  test("has no WCAG 2.2 A or AA violations on a real dossier", async ({ page }) => {
    await page.goto(NVIDIA);
    await expect(page.getByText("Research forecast, not approved for the product")).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations).toEqual([]);
  });

  test("fits a phone without sideways scrolling", async ({ page }, info) => {
    test.skip(info.project.name !== "mobile", "phone layout only");
    await page.goto(NVIDIA);
    await expect(page.getByText("Research forecast, not approved for the product")).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
