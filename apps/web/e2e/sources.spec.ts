import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { type Locator, type Page, expect, test } from "@playwright/test";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const SCREENS_DIR = fileURLToPath(
  new URL(`../../../docs/stages/${process.env["SAVE_SCREENS"] ?? "screens"}/`, import.meta.url),
);

async function saveScreen(page: Page, name: string, part?: Locator): Promise<void> {
  if (!process.env["SAVE_SCREENS"]) return;
  mkdirSync(SCREENS_DIR, { recursive: true });
  const path = `${SCREENS_DIR}${name}-${test.info().project.name}.png`;
  await (part ? part.screenshot({ path }) : page.screenshot({ path }));
}

async function expectNoViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  expect(results.violations.map((violation) => violation.id)).toEqual([]);
}

test.describe("Data Catalog", () => {
  test("lists the sources by access category with downloads off", async ({ page }) => {
    await page.goto("/data-catalog");
    await expect(page.getByRole("heading", { level: 1, name: "Data Catalog" })).toBeVisible();
    await expect(page.getByRole("status")).toHaveText("4 of 4 sources");
    await expect(page.getByRole("heading", { level: 3, name: "Public access" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Free API key" })).toBeVisible();
    await expect(page.getByText("Downloads off, awaiting the owner's decision")).toHaveCount(4);
    await expect(page.getByRole("heading", { name: "Licensed data" })).toBeVisible();
    await expect(page.getByText("No data has been downloaded")).toBeVisible();
    await saveScreen(page, "data-catalog");
    await expectNoViolations(page);
  });

  test("searches the data dictionary and filters by access", async ({ page }) => {
    await page.goto("/data-catalog");
    await page.getByRole("searchbox", { name: "Search" }).fill("realtime_start");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page).toHaveURL(/q=realtime_start/);
    await expect(page.getByRole("status")).toHaveText("1 of 4 sources");
    await expect(page.getByRole("link", { name: "FRED and ALFRED" })).toBeVisible();
    await expect(page.getByText(/Field realtime_start in Series observations/)).toBeVisible();

    await page.getByRole("searchbox", { name: "Search" }).fill("");
    await page.getByRole("combobox", { name: "Access" }).selectOption("api_key");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("1 of 4 sources");
    await expect(page.getByRole("heading", { name: "Licensed data" })).toHaveCount(0);
    await saveScreen(page, "data-catalog-search");
  });

  test("explains an empty result and ignores an unknown filter", async ({ page }) => {
    await page.goto("/data-catalog?q=bloomberg&access=everything");
    await expect(page.getByText("No source matches “bloomberg”.")).toBeVisible();
    await expect(page.getByText("Unsupported values for: access.")).toBeVisible();
  });

  test("shows the SEC contract: User-Agent, throttle, retries, checksums and docs", async ({
    page,
  }) => {
    await page.goto("/data-catalog/sec-edgar");
    await expect(page.getByRole("heading", { level: 1, name: "SEC EDGAR" })).toBeVisible();
    await expect(page.getByText("2 requests per second at most")).toBeVisible();
    await expect(page.getByText(/No more than 10 requests per second/)).toBeVisible();
    await expect(page.getByText(/Declare a User-Agent/)).toBeVisible();
    await expect(page.getByText(/Stop the whole run on 403/)).toBeVisible();
    const docs = page.getByRole("link", { name: /EDGAR application programming interfaces/ });
    await expect(docs.first()).toHaveAttribute(
      "href",
      "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    );
    await expect(docs.first()).toHaveAttribute("rel", "noopener noreferrer");
    const dictionary = page.getByRole("region", {
      name: "Data dictionary: Submissions (filing history)",
    });
    await expect(
      dictionary.getByRole("rowheader", { name: "filings.recent.acceptanceDateTime" }),
    ).toBeVisible();
    await saveScreen(page, "data-catalog-sec");
    await expectNoViolations(page);
  });

  test("marks FRED as key-based and its vintages as knowledge time", async ({ page }) => {
    await page.goto("/data-catalog/fred-alfred");
    await expect(page.getByText("Key needed: the owner registers")).toBeVisible();
    await expect(page.getByText("Resale").first()).toBeVisible();
    const observations = page.getByRole("region", {
      name: "Data dictionary: Series observations with vintages",
    });
    await expect(observations.getByRole("row", { name: /realtime_start/ })).toContainText(
      "Knowledge time",
    );
  });

  test("answers 404 for an unknown source", async ({ page }) => {
    const response = await page.goto("/data-catalog/bloomberg");
    expect(response?.status()).toBe(404);
  });

  test("shows the plan, the risk register and the first ten companies", async ({ page }) => {
    await page.goto("/data-catalog/plan");
    await expect(page.getByRole("heading", { level: 1, name: "Acquisition plan" })).toBeVisible();
    await expect(page.getByText("Real companies, no data yet")).toBeVisible();
    await expect(page.getByText("Owner decision needed").first()).toBeVisible();
    const risks = page.getByRole("region", { name: "15 risks" });
    await expect(risks.locator("tbody tr")).toHaveCount(15);
    const candidates = page.getByRole("region", { name: "Candidates for the first acquisition" });
    await expect(candidates.locator("tbody tr")).toHaveCount(10);
    await expect(candidates.getByRole("row", { name: /Celgene/ })).toContainText("No ticker");
    await expect(candidates.getByRole("row", { name: /Celgene/ })).toContainText("Acquired");
    await saveScreen(page, "data-catalog-plan");
    await saveScreen(page, "data-catalog-risks", risks);
    await saveScreen(page, "data-catalog-companies", candidates);
    await expectNoViolations(page);
  });
});

test.describe("Data Catalog without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("searches with the plain form", async ({ page }) => {
    await page.goto("/data-catalog");
    await page.getByRole("searchbox", { name: "Search" }).fill("sdmx");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("1 of 4 sources");
    await expect(page.getByRole("link", { name: "ECB Data Portal (SDMX)" })).toBeVisible();
  });
});
