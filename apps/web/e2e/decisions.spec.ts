import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

async function saveScreen(page: Page, name: string, fullPage = false): Promise<void> {
  const folder = process.env["SAVE_SCREENS"];
  if (!folder) return;
  const dir = fileURLToPath(new URL(`../../../docs/stages/${folder}/`, import.meta.url));
  mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: `${dir}${name}.png`, fullPage });
}

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const NORTHWIND = "5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13";
const TESSARACT = "0f6a2c8e-9b1d-4e53-a7c4-58d2e1b9f036";
const VALTRIX = "8d2c6e1a-4f9b-4b70-8e3d-c5a1f7b2e906";
const builder = (company: string, type = "rnd_change") =>
  `/decisions?company=${company}&type=${type}`;

async function validate(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Validation", level: 2 })).toBeFocused();
}

test.describe("Decision Builder", () => {
  test("starts from a company and keeps the cutoff and type in the link", async ({ page }) => {
    await page.goto("/decisions");
    await page.getByRole("link", { name: /Northwind Semiconductors/ }).click();
    await expect(page.getByText("Company:")).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Known as of" })).toHaveValue("2022-12-31");
    await page.getByRole("radio", { name: /CAPEX expansion/ }).check();
    await expect(page).toHaveURL(/type=capex_expansion/);
    await expect(page.getByRole("region", { name: /How capex expansion works/ })).toBeVisible();
  });

  test("requires a unit for R&D, then shows both meanings in dollars (US-03)", async ({ page }) => {
    await page.goto(builder(NORTHWIND));
    await page.getByRole("textbox", { name: /^R&D change/ }).fill("40");
    await validate(page);
    await expect(page.getByTestId("validation-status")).toContainText("1 error blocks a run");
    await saveScreen(page, `decision-errors-${test.info().project.name}`);

    await page.getByRole("link", { name: /Choose what the number is measured against/ }).click();
    const unit = page.getByRole("combobox", { name: /Measured against/ });
    await expect(unit).toBeFocused();
    await unit.selectOption({ label: "% of the previous R&D budget" });
    await validate(page);
    await expect(page.getByTestId("validation-status")).toContainText("No blocking errors");
    await expect(page.getByText("Change in yearly R&D spending")).toBeVisible();
    await expect(page.getByText("Same change in percentage points of revenue")).toBeVisible();
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();
    await page.getByText("Change in yearly R&D spending").scrollIntoViewIfNeeded();
    await saveScreen(page, `decision-valid-${test.info().project.name}`);
  });

  test("rejects a value above the hard limit and warns outside the planning range", async ({
    page,
  }) => {
    await page.goto(builder(NORTHWIND));
    await page
      .getByRole("combobox", { name: /Measured against/ })
      .selectOption("fraction_of_previous_rnd_budget");
    const value = page.getByRole("textbox", { name: /^R&D change/ });
    await value.fill("600");
    await validate(page);
    await expect(
      page
        .getByText(
          "Enter a value from −90% of the previous R&D budget to +500% of the previous R&D budget.",
        )
        .first(),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeDisabled();

    await value.fill("300");
    await validate(page);
    await expect(page.getByTestId("validation-status")).toContainText("No blocking errors");
    await expect(page.getByText(/Outside the planning range/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();
  });

  test("keeps financing shares at exactly 100% and never normalizes them (US-04)", async ({
    page,
  }) => {
    await page.goto(builder(NORTHWIND, "acquisition"));
    await page.getByRole("textbox", { name: "Cash on hand" }).fill("60");
    await page.getByRole("textbox", { name: "New debt", exact: true }).fill("30");
    await page.getByRole("textbox", { name: "New equity" }).fill("5");
    await expect(page.getByText("Total 95%. It must be exactly 100%.")).toBeVisible();
    await validate(page);
    await expect(
      page.getByText("Financing shares add up to 95%. They must add up to exactly 100%.").first(),
    ).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Cash on hand" })).toHaveValue("60");
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeDisabled();

    await page.getByRole("textbox", { name: "New debt", exact: true }).fill("40");
    await page.getByRole("textbox", { name: "New equity" }).fill("0");
    await expect(page.getByText("Total 100%.")).toBeVisible();
    await validate(page);
    await expect(page.getByTestId("validation-status")).toContainText("No blocking errors");
    await expect(page.getByText("Total funding need")).toBeVisible();

    await page.getByRole("button", { name: "Run", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Ready to run" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Scenario JSON")).toContainText('"cash": "0.6"');
    await expect(dialog.getByLabel("Scenario JSON")).toContainText('"type": "acquisition"');
    await saveScreen(page, `decision-run-${test.info().project.name}`);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("marks a result stale when the cutoff changes (FR-TM-03)", async ({ page }) => {
    await page.goto(builder(NORTHWIND, "capex_expansion"));
    await validate(page);
    await expect(page.getByTestId("validation-status")).toContainText("No blocking errors");
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();

    await page.getByRole("combobox", { name: "Known as of" }).selectOption("2022-06-30");
    await expect(page.getByText("Stale — requires rerun").first()).toBeVisible();
    await expect(page.getByText(/changed from 2022-12-31 to 2022-06-30/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeDisabled();
    await expect(page.getByRole("textbox", { name: "Announced on" })).toHaveValue("2022-06-30");
    await page.getByText(/changed from 2022-12-31/).scrollIntoViewIfNeeded();
    await saveScreen(page, `decision-stale-${test.info().project.name}`);

    await validate(page);
    await expect(page.getByText("Stale — requires rerun")).toHaveCount(0);
    await expect(page.getByText("Checked for the cutoff 2022-06-30.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();
  });

  test("resets a decision to its documented defaults", async ({ page }) => {
    await page.goto(builder(NORTHWIND, "debt_refinance"));
    const fees = page.getByRole("textbox", { name: "Fees" });
    await expect(fees).toHaveValue("1");
    await fees.fill("4");
    await page.getByRole("button", { name: "Reset to defaults" }).click();
    await expect(fees).toHaveValue("1");
    await expect(
      page.getByRole("status").filter({ hasText: "reset to the documented defaults" }),
    ).toBeVisible();
  });

  test("rejects an announcement before the knowledge cutoff", async ({ page }) => {
    await page.goto(builder(NORTHWIND, "workforce_restructure"));
    await page.getByRole("textbox", { name: "Announced on" }).fill("2022-12-01");
    await validate(page);
    await expect(
      page
        .getByText("A decision made at the cutoff 2022-12-31 cannot be announced before it.")
        .first(),
    ).toBeVisible();
  });

  test("moves a slider with the keyboard and updates the number", async ({ page }) => {
    await page.goto(builder(NORTHWIND, "capex_expansion"));
    const slider = page.getByRole("slider", { name: "Horizon, slider" });
    await slider.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("textbox", { name: "Horizon" })).toHaveValue("21");
    await expect(slider).toHaveAttribute("aria-valuetext", "21 quarters");
  });

  test("warns about insufficient history but allows a demo (FC-02)", async ({ page }) => {
    await page.goto(builder(TESSARACT, "capex_expansion"));
    await validate(page);
    await expect(
      page
        .getByText(/Insufficient history: 6 of the 8 quarters needed were public by 2022-12-31/)
        .first(),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();
  });

  test("has no WCAG 2.2 A or AA violations with errors on screen", async ({ page }) => {
    await page.goto(builder(NORTHWIND, "acquisition"));
    await page.getByRole("textbox", { name: "New equity" }).fill("5");
    await validate(page);
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });
});

test.describe("Decision Builder screens", () => {
  test.skip(!process.env["SAVE_SCREENS"], "Only when saving QA screenshots");

  test("captures each part of the form", async ({ page }) => {
    await page.goto(builder(NORTHWIND, "acquisition"));
    for (const [heading, name] of [
      ["Size and timing", "size"],
      ["Assumptions", "assumptions"],
      ["Financing", "financing"],
    ] as const) {
      await page.getByRole("heading", { name: heading, level: 2 }).scrollIntoViewIfNeeded();
      await page.evaluate(() => window.scrollBy(0, -80));
      await saveScreen(page, `decision-${name}-${test.info().project.name}`);
    }
  });
});

test.describe("Decision Builder edge cases", () => {
  test("explains an unsupported company and shows no form", async ({ page }) => {
    await page.goto(`/decisions?company=${VALTRIX}`);
    await expect(page.getByText("This company is not supported yet")).toBeVisible();
    await expect(page.getByRole("button", { name: "Validate" })).toHaveCount(0);
  });

  test("ignores unsafe link parameters without echoing them", async ({ page }) => {
    await page.goto("/decisions?company=%3Cscript%3E&type=price_increase&asOf=2099-01-01");
    await expect(page.getByText("Unsupported values for: company, asOf, type.")).toBeVisible();
    await expect(page.locator("main")).not.toContainText("<script>");
    await expect(page.getByRole("heading", { name: "Choose a company" })).toBeVisible();
  });

  test("is linked from the company dossier", async ({ page }) => {
    await page.goto(`/dossier/${NORTHWIND}?asOf=2022-06-30`);
    await page.getByRole("link", { name: "Build a decision for this company" }).click();
    await expect(page).toHaveURL(new RegExp(`company=${NORTHWIND}&asOf=2022-06-30`));
    await expect(page.getByRole("combobox", { name: "Known as of" })).toHaveValue("2022-06-30");
  });
});

test.describe("Assumption Matrix", () => {
  test("documents every parameter with its range, default and source", async ({ page }) => {
    await page.goto("/assumptions");
    await expect(page.getByRole("heading", { level: 2 })).toHaveCount(6);
    await expect(page.getByRole("region", { name: /R&D budget change: parameters/ })).toContainText(
      "Accounting rule",
    );
    await expect(
      page.getByRole("region", { name: /Divestiture or segment exit: parameters/ }),
    ).toContainText("Statutory rate");
    await expect(page.getByText(/Placeholder, not an estimate/).first()).toBeVisible();
  });
});
