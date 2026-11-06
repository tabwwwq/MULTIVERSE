import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Causal Map", () => {
  test("says that no effect is estimated, in the header and in the first section", async ({
    page,
  }) => {
    await page.goto("/causal-map");
    await expect(page.getByRole("heading", { level: 1, name: "Causal Map" })).toBeVisible();
    await expect(page.getByText("Feasibility study, no effect estimated")).toBeVisible();
    await expect(page.getByText("No effect is estimated here")).toBeVisible();
  });

  test("draws the graph and describes it in words", async ({ page }) => {
    await page.goto("/causal-map");
    await expect(page.getByRole("img", { name: /Hypothesised causes/ })).toBeVisible();
    await page.getByText("The graph in words, and what it leaves out").click();
    await expect(page.getByText(/expectations to action/)).toBeVisible();
    await expect(page.getByText(/Left out:/).first()).toBeVisible();
  });

  test("shows why a method is closed", async ({ page }) => {
    await page.goto("/causal-map");
    const layoff = page
      .locator("details")
      .filter({ has: page.locator("summary", { hasText: /^Layoff$/ }) });
    await layoff.locator("summary").click();
    await expect(layoff.getByText(/usable events, 30 are needed/).first()).toBeVisible();
    await expect(layoff.getByText(/Never testable here/)).toBeVisible();
  });

  test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
    await page.goto("/causal-map");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
