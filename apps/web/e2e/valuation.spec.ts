import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const AXE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

test.describe("Valuation Studio", () => {
  test("says what the value is not before any number", async ({ page }) => {
    await page.goto("/valuation");
    await expect(page.getByRole("heading", { level: 1, name: "Valuation Studio" })).toBeVisible();
    const main = page.locator("main");
    await expect(main).toContainText("Model value, not a verified market value");
    await expect(main).toContainText("Price per share is not shown");
    await expect(main).not.toContainText(/fair market value/i);
  });

  test("keeps enterprise value and equity value apart, with the bridge", async ({ page }) => {
    await page.goto("/valuation");
    await expect(page.getByText("Enterprise value (DCF, model)").first()).toBeVisible();
    await expect(page.getByText("Equity value (model)").first()).toBeVisible();
    await expect(page.getByRole("img", { name: /Bridge from enterprise value/ })).toBeVisible();
  });

  test("refuses WACC at or below growth, with the reason", async ({ page }) => {
    await page.goto("/valuation");
    await page.getByLabel("Terminal growth, %").fill("20");
    await expect(page.getByText("This setting has no value")).toBeVisible();
    await expect(page.getByText(/has no finite value/)).toBeVisible();
    await expect(page.getByText("Enterprise value (DCF, model)")).toHaveCount(0);
    await page.getByRole("button", { name: "Back to the report values" }).click();
    await expect(page.getByText("Enterprise value (DCF, model)").first()).toBeVisible();
  });

  test("a parameter changes the value at once", async ({ page }) => {
    await page.goto("/valuation");
    const value = page.locator("[aria-live=polite]").first();
    const before = await value.innerText();
    await page.getByLabel("Beta").fill("1.5");
    await expect(value).not.toHaveText(before);
  });

  test("offers the exit multiple and compares the two methods", async ({ page }) => {
    await page.goto("/valuation");
    await page.getByLabel("Method", { exact: true }).selectOption("exit_multiple");
    await expect(page.getByLabel("Exit multiple, EV / EBITDA")).toBeVisible();
    await expect(page.getByText("Terminal methods compared")).toBeVisible();
    await expect(page.getByText(/implied growth/).first()).toBeVisible();
    await expect(page.getByText(/Terminal value is/)).toBeVisible();
  });

  test("an ill-defined share count is refused and no price appears", async ({ page }) => {
    await page.goto("/valuation");
    await expect(page.getByText(/keep 100\.00% of equity value/)).toBeVisible();
    await page.getByLabel("Diluted shares, million").fill("0");
    await expect(page.getByText("Ill-defined share count")).toBeVisible();
    await expect(page.locator("main")).not.toContainText(/per share:/i);
  });

  test("shows the DCF by year and by quarter, and the matrix", async ({ page }) => {
    await page.goto("/valuation");
    await expect(page.getByRole("region", { name: /by year/ })).toBeVisible();
    await page.getByRole("button", { name: "Show quarters" }).click();
    await expect(page.getByRole("region", { name: /by quarter/ })).toBeVisible();
    await expect(page.getByRole("region", { name: "Sensitivity matrix" })).toBeVisible();
  });

  test("gives the DCF and the matrix as CSV", async ({ page }) => {
    await page.goto("/valuation");
    const [dcf] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download DCF as CSV" }).click(),
    ]);
    expect(dcf.suggestedFilename()).toBe("multiverse_dcf_MODEL.csv");
    const [grid] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download matrix as CSV" }).click(),
    ]);
    expect(grid.suggestedFilename()).toBe("multiverse_sensitivity_MODEL.csv");
  });

  test("shows the tornado as not causal, the method and the checks", async ({ page }) => {
    await page.goto("/valuation");
    await expect(page.getByText(/Predictive sensitivity, not causal/)).toBeVisible();
    await expect(
      page.getByRole("img", { name: /Change of enterprise value by driver/ }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Method and assumptions" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Quality protocol" })).toBeVisible();
    const checks = page.getByRole("region", { name: "Quality protocol" });
    await expect(checks.getByText("Warning").locator("visible=true").first()).toBeVisible();
  });

  test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
    await page.goto("/valuation");
    const results = await new AxeBuilder({ page }).withTags(AXE).analyze();
    expect(results.violations).toEqual([]);
  });

  test("has no WCAG 2.2 violations with a refusal on screen", async ({ page }) => {
    await page.goto("/valuation");
    await page.getByLabel("Terminal growth, %").fill("20");
    await page.getByText("This setting has no value").waitFor();
    const results = await new AxeBuilder({ page }).withTags(AXE).analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("Risk Observatory", () => {
  test("says the shares are conditional before any number", async ({ page }) => {
    await page.goto("/risk");
    await expect(page.getByRole("heading", { level: 1, name: "Risk Observatory" })).toBeVisible();
    const main = page.locator("main");
    await expect(main).toContainText("Conditional on the assumed model, not validated");
    await expect(main).toContainText("not a plan of");
    await expect(page.getByText("Under the assumed model").first()).toBeVisible();
  });

  test("shows bear, base and bull with a figure and a table", async ({ page }) => {
    await page.goto("/risk");
    await expect(page.getByRole("img", { name: /Enterprise value by scenario/ })).toBeVisible();
    await expect(page.getByText(/Weighted enterprise value \(model\)/)).toBeVisible();
  });

  test("refuses weights that are not a whole", async ({ page }) => {
    await page.goto("/risk");
    await page.getByLabel("Bear weight, %").fill("60");
    await expect(page.getByText("These weights are not a whole")).toBeVisible();
    await page.getByLabel("Bear weight, %").fill("25");
    await expect(page.getByText(/Weighted enterprise value \(model\)/)).toBeVisible();
  });

  test("explains the worst stress from the numbers of its path", async ({ page }) => {
    await page.goto("/risk");
    const story = page.getByRole("region", { name: /What the worst stress does/ });
    await expect(story.getByRole("listitem").first()).toContainText("Revenue falls 20%");
    await expect(story).toContainText("Net debt / EBITDA peaks");
    await expect(story).toContainText("conditional on the assumed model");
  });

  test("gives the stress cases as CSV", async ({ page }) => {
    await page.goto("/risk");
    const [file] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download stress cases as CSV" }).click(),
    ]);
    expect(file.suggestedFilename()).toBe("multiverse_stress_MODEL.csv");
  });

  test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
    await page.goto("/risk");
    const results = await new AxeBuilder({ page }).withTags(AXE).analyze();
    expect(results.violations).toEqual([]);
  });
});
