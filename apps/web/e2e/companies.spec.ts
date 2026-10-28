import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";

async function saveScreen(page: Page, name: string): Promise<void> {
  const folder = process.env["SAVE_SCREENS"];
  if (!folder) return;
  const dir = fileURLToPath(new URL(`../../../docs/stages/${folder}/`, import.meta.url));
  mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: `${dir}${name}.png` });
}

const NORTHWIND = "/dossier/5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13";
const KESTREL = "/dossier/e4b8d0a2-7c3f-4196-b2e5-9a0c6d1f8e47";
const VALTRIX = "/dossier/8d2c6e1a-4f9b-4b70-8e3d-c5a1f7b2e906";
const TESSARACT = "/dossier/0f6a2c8e-9b1d-4e53-a7c4-58d2e1b9f036";

test.describe("Universe Explorer", () => {
  test("lists the seven synthetic demo companies", async ({ page }) => {
    await page.goto("/universe");
    await expect(page.getByRole("status").filter({ hasText: "companies" })).toHaveText(
      "7 of 7 companies",
    );
    await expect(page.getByRole("heading", { level: 3 })).toHaveCount(7);
    await expect(page.getByText("Demo universe of seven fictional companies")).toBeVisible();
  });

  test("searches as you type with the keyboard and keeps focus in the field", async ({ page }) => {
    await page.goto("/universe");
    const field = page.getByRole("searchbox", { name: "Search" });
    await field.focus();
    await page.keyboard.type("nwmd");
    await expect(page.getByRole("status").filter({ hasText: "companies" })).toHaveText(
      "1 of 7 companies",
    );
    await expect(field).toBeFocused();
    await expect(page).toHaveURL(/q=nwmd/);
    await expect(page.getByText("Matched former ticker NWMD, used until 2019-06-30")).toBeVisible();

    const result = page.getByRole("link", { name: "Northwind Semiconductors Inc." });
    await result.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`${NORTHWIND}$`));
  });

  test("finds a company by CIK without leading zeros", async ({ page }) => {
    await page.goto("/universe?q=99000106");
    await expect(page.getByRole("link", { name: "Kestrel Instruments Ltd." })).toBeVisible();
    await expect(page.getByText("Matched CIK 0099000106")).toBeVisible();
  });

  test("shows an empty state for a search without results", async ({ page }) => {
    await page.goto("/universe?q=zzzz");
    await expect(page.getByRole("status").filter({ hasText: "companies" })).toHaveText(
      "0 of 7 companies",
    );
    await expect(page.getByText("No company matches “zzzz”")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Clear search and filters" }).last(),
    ).toHaveAttribute("href", "/universe");
  });

  test("explains that a real ticker is not in the demo universe", async ({ page }) => {
    await page.goto("/universe?q=AAPL");
    await expect(page.getByText("No company matches “AAPL”")).toBeVisible();
    await expect(page.getByText(/real tickers such as AAPL are not found yet/)).toBeVisible();
  });

  test("filters by lifecycle and coverage", async ({ page }) => {
    await page.goto("/universe?status=acquired");
    await expect(page.getByRole("heading", { level: 3 })).toHaveText([
      "Aurora Grid Utilities Corp.",
    ]);
    await page.goto("/universe?coverage=under-8");
    await expect(page.getByRole("heading", { level: 3 })).toHaveCount(2);
  });

  test("ignores unsafe link parameters without echoing them", async ({ page }) => {
    let dialogOpened = false;
    page.on("dialog", (dialog) => {
      dialogOpened = true;
      void dialog.dismiss();
    });
    await page.goto(
      "/universe?sector=%3Cscript%3Ealert(1)%3C%2Fscript%3E&country=Germany&status=zombie",
    );
    await expect(page.getByText("Some filters in the link were ignored")).toBeVisible();
    await expect(page.getByText("Unsupported values for: sector, country, status.")).toBeVisible();
    await expect(page.locator("main")).not.toContainText("<script>");
    expect(dialogOpened).toBe(false);
    await expect(page.getByRole("status").filter({ hasText: "companies" })).toHaveText(
      "7 of 7 companies",
    );
  });

  test("shortens a very long search text", async ({ page }) => {
    await page.goto(`/universe?q=${"a".repeat(300)}`);
    await expect(page.getByText("Search text was shortened to 64 characters")).toBeVisible();
    await expect(page.getByRole("searchbox", { name: "Search" })).toHaveValue("a".repeat(64));
  });
});

test.describe("Universe Explorer without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("still searches through the plain GET form", async ({ page }) => {
    await page.goto("/universe");
    await page.getByRole("searchbox", { name: "Search" }).fill("kestrel");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page).toHaveURL(/q=kestrel/);
    await expect(page.getByRole("heading", { level: 3 })).toHaveText(["Kestrel Instruments Ltd."]);
  });
});

test.describe("Company Dossier", () => {
  test("separates the stable ID from the ticker and name history", async ({ page }) => {
    await page.goto(NORTHWIND);
    await expect(page.getByText("5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13")).toBeVisible();
    await expect(page.getByText(/NWMD\s+on NASDAQ, 2012-03-01 to 2019-06-30/)).toBeVisible();
    await expect(page.getByText(/NWSC\s+on NASDAQ, since 2019-07-01/)).toBeVisible();
    const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(crumbs.getByText("Company profile")).toHaveAttribute("aria-current", "page");
  });

  test("shows the lineage of a value in a toggletip", async ({ page }) => {
    await page.goto(NORTHWIND);
    await page.getByRole("button", { name: /Revenue, FY2022 Q4\. Show lineage$/ }).click();
    const popover = page.locator("#lineage-revenue-2022-q4");
    await expect(popover).toBeVisible();
    await expect(popover).toContainText("us-gaap:Revenues");
    await expect(popover).toContainText("Fiscal year minus the first nine months");
    await expect(popover).toContainText("10-K");
    await expect(popover).toContainText("None: this filing is synthetic");
    await saveScreen(page, `lineage-${test.info().project.name}`);
    await page.keyboard.press("Escape");
    await expect(popover).toBeHidden();
  });

  test("shows a missing value as missing with its reason, never as zero", async ({ page }) => {
    await page.goto(NORTHWIND);
    const button = page.getByRole("button", {
      name: "Missing, R&D expense, FY2021 Q3. Show lineage",
    });
    await expect(button).toHaveText("—");
    await button.click();
    await expect(page.locator("#lineage-rnd_expense-2021-q3")).toContainText(
      "not tagged separately",
    );
  });

  test("hides values that were not public yet at the chosen cutoff", async ({ page }) => {
    await page.goto(`${NORTHWIND}?asOf=2022-06-30`);
    await page.getByRole("region", { name: /Quarterly results/ }).scrollIntoViewIfNeeded();
    await saveScreen(page, `dossier-as-of-${test.info().project.name}`);
    await expect(
      page.getByText(/values were filed later and are marked as not public/),
    ).toBeVisible();
    const button = page.getByRole("button", {
      name: "Not public yet, Revenue, FY2022 Q2. Show lineage",
    });
    await button.click();
    await expect(page.locator("#lineage-revenue-2022-q2")).toContainText(
      "Not public on 2022-06-30: filed on 2022-08-",
    );
  });

  test("changes the cutoff and the amount scale from the controls", async ({ page }) => {
    await page.goto(NORTHWIND);
    await page.getByRole("combobox", { name: "Known as of" }).selectOption("2021-12-31");
    await page.getByRole("button", { name: "Show", exact: true }).click();
    await expect(page).toHaveURL(/asOf=2021-12-31/);
    await expect(page.getByRole("rowheader").first()).toContainText("FY2021 Q4");
    // The quarter ended on the cutoff, but its 10-K was filed later: not public yet.
    await expect(
      page.getByRole("button", { name: "Not public yet, Revenue, FY2021 Q4. Show lineage" }),
    ).toBeVisible();

    await page.getByRole("link", { name: "USD bn" }).click();
    await expect(page).toHaveURL(/scale=bn/);
    await expect(page.getByRole("link", { name: "USD bn" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    await expect(
      page.getByRole("button", { name: /^\d+\.\d{2} USD bn, Revenue, FY2021 Q3/ }),
    ).toBeVisible();
  });

  test("ignores an invalid cutoff or scale in the link", async ({ page }) => {
    await page.goto(`${NORTHWIND}?asOf=2099-01-01&scale=trillion`);
    await expect(page.getByText("Unsupported values for: asOf, scale.")).toBeVisible();
    await expect(page.getByRole("rowheader").first()).toContainText("FY2022 Q4");
  });

  test("keeps quarters before a reporting currency change missing instead of converting", async ({
    page,
  }) => {
    await page.goto(KESTREL);
    await expect(
      page.getByText(/Reporting currency changed from CAD to USD at the start of FY2021/),
    ).toBeVisible();
    await page.getByRole("button", { name: "Missing, Revenue, FY2020 Q1. Show lineage" }).click();
    await expect(page.locator("#lineage-revenue-2020-q1")).toContainText("Reported in CAD");
  });

  test("explains an unsupported company and shows no financial values", async ({ page }) => {
    await page.goto(VALTRIX);
    await expect(page.getByText("This company is not supported yet")).toBeVisible();
    await expect(page.getByText(/Form 20-F under IFRS in EUR/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Financial history" })).toHaveCount(0);
    await expect(page.getByRole("region", { name: /Filings behind the values/ })).toContainText(
      "20-F",
    );
  });

  test("warns when the history is too short", async ({ page }) => {
    await page.goto(TESSARACT);
    // The support badge and the alert title both say it.
    await expect(page.getByText("Insufficient history", { exact: true })).toHaveCount(2);
    await expect(page.getByText(/7 of the 8 fiscal quarters/)).toBeVisible();
  });

  test("answers 404 for an unknown company ID", async ({ page }) => {
    const response = await page.goto("/dossier/00000000-0000-4000-8000-000000000000");
    expect(response?.status()).toBe(404);
  });
});
