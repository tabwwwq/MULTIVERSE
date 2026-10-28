import { mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

async function saveScreen(page: Page, name: string): Promise<void> {
  const folder = process.env["SAVE_SCREENS"];
  if (!folder) return;
  const dir = fileURLToPath(new URL(`../../../docs/stages/${folder}/`, import.meta.url));
  mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: `${dir}${name}.png` });
}

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const RND = "2d7c9e41-5b3a-4f6e-8c1d-9a0b7e6f5c34";
const CAPEX = "8a4f6c2e-1d3b-4e5a-9f7c-2b6d8e0a1c53";
const WORKFORCE = "c3e5a7b9-2f4d-4c6e-8a0b-5d7f9e1c3a62";
const FAILED = "6f1d2b8a-3c4e-4a5f-9b7d-1e2c3a4b5d6e";
const chartGroup = (page: Page) =>
  page.getByRole("group", { name: /Revenue|EBITDA|FCF|Net debt|EV/ });

test.describe("Timeline Explorer", () => {
  test("shows history, baseline and both alternates with mock labels", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    for (const key of ["observed", "baseline", "alt_a", "alt_b"]) {
      await expect(page.getByTestId(`line-${key}`)).toBeAttached();
    }
    await expect(page.getByTestId("band-alt_b")).toBeAttached();
    await expect(page.getByText("Synthetic · mock")).toBeVisible();
    await expect(page.getByText("History (reported)")).toBeVisible();
    await expect(
      page.getByText(/not calibrated: they are not a confidence interval/),
    ).toBeVisible();
    await expect(page.getByRole("main").getByText("Mode", { exact: true })).toBeVisible();
    await page.getByTestId("timeline-svg").scrollIntoViewIfNeeded();
    await saveScreen(page, `timeline-chart-${test.info().project.name}`);
  });

  test("KPI cards show the same numbers as the chart summary (FR-RE-07)", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    const median = await page.getByTestId("kpi-baseline-median").textContent();
    await expect(page.getByText(`Baseline: median ${median}`)).toBeVisible();
    await expect(page.getByTestId("kpi-baseline")).toContainText("FY2025 Q3");
  });

  test("switches to paired changes and keeps the choice in the link", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    await page.getByText("Change vs baseline").click();
    await expect(page).toHaveURL(/mode=change/);
    await expect(page.getByTestId("line-observed")).toHaveCount(0);
    await expect(page.getByTestId("kpi-baseline")).toHaveCount(0);
    await expect(page.getByTestId("kpi-alt_b-median")).toContainText("+USD");
    await expect(page.getByText(/computed path by path against the paired baseline/)).toBeVisible();
    await saveScreen(page, `timeline-change-${test.info().project.name}`);
  });

  test("disables percent where the baseline can cross zero (FP-08)", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    await page.getByText("Net debt", { exact: true }).click();
    await expect(page.getByRole("radio", { name: "Percent vs baseline" })).toBeDisabled();
    await expect(page.getByText(/Undefined for net debt/)).toBeVisible();
  });

  test("hides a series from the legend without repainting the others", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    const strokeA = await page.getByTestId("line-alt_a").getAttribute("stroke");
    const toggle = page.getByRole("button", { name: "R&D +40% (mock)" });
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(page.getByTestId("line-alt_b")).toHaveCount(0);
    await expect(page.getByTestId("line-alt_a")).toHaveAttribute("stroke", strokeA ?? "");
  });

  test("reads every quarter with the keyboard and announces it", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    const chart = chartGroup(page);
    await chart.focus();
    await page.keyboard.press("End");
    const tooltip = page.getByTestId("chart-tooltip");
    await expect(tooltip).toContainText("FY2025 Q3");
    await expect(tooltip).toContainText("Mock quantiles p10 to p90");
    await page.keyboard.press("Home");
    await expect(tooltip).toContainText(/source .+, filed \d{4}-\d{2}-\d{2}/);
    await expect(
      page.locator("[aria-live=polite]").filter({ hasText: "Observed:" }),
    ).toBeAttached();
    await page.keyboard.press("Escape");
    await expect(tooltip).toHaveCount(0);
  });

  test("shows the readout on hover with units", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    // The mouse does not scroll: bring the chart into view first.
    await page.getByTestId("timeline-svg").scrollIntoViewIfNeeded();
    const box = await page.getByTestId("timeline-svg").boundingBox();
    if (!box) throw new Error("chart not rendered");
    await page.mouse.move(box.x + box.width * 0.85, box.y + box.height * 0.5);
    await expect(page.getByTestId("chart-tooltip")).toContainText("USD");
    await saveScreen(page, `timeline-tooltip-${test.info().project.name}`);
  });

  test("offers every plotted point as a table and as a CSV", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    await page.getByRole("button", { name: "Show as table" }).click();
    const table = page.getByRole("region", { name: /every plotted point/ });
    await expect(table).toBeVisible();
    // 11 reported quarters and 12 forecast quarters; the card layout on phones hides the header row.
    await expect(table.locator("tbody tr")).toHaveCount(11 + 12);

    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download CSV" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/_revenue_absolute_DEMO\.csv$/);
    const path = await file.path();
    const text = readFileSync(path, "utf8");
    expect(text.split("\n")[0]).toMatch(/^# SYNTHETIC DEMO DATA/);
    expect(text).toContain("period_end,fiscal_label,series,kind,p10,p50,p90,unit,source");
  });

  test("keeps zero on the axis in absolute mode (FP-09)", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    await expect(page.getByTestId("timeline-svg").getByText("0", { exact: true })).toBeAttached();
  });

  test("has no WCAG 2.2 A or AA violations with the table open", async ({ page }) => {
    await page.goto(`/timeline/${RND}?metric=ebitda&mode=change`);
    await page.getByRole("button", { name: "Show as table" }).click();
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });

  test("lists the decision events", async ({ page }) => {
    await page.goto(`/timeline/${RND}`);
    await expect(page.getByRole("heading", { name: "Event timeline" })).toBeVisible();
    await expect(page.getByText("R&D +40%: full effect")).toBeVisible();
  });
});

test.describe("Result states", () => {
  test("explains a failed run without numbers", async ({ page }) => {
    await page.goto(`/timeline/${FAILED}`);
    await expect(page.getByText("This run failed")).toBeVisible();
    await expect(page.getByText("INC-MOCK-0001")).toBeVisible();
    await expect(page.getByTestId("timeline-svg")).toHaveCount(0);
    await saveScreen(page, `timeline-failed-${test.info().project.name}`);
  });

  test("answers 404 for an unknown result", async ({ page }) => {
    const response = await page.goto("/timeline/00000000-0000-4000-8000-000000000000");
    expect(response?.status()).toBe(404);
  });

  test("ignores unsafe link values", async ({ page }) => {
    await page.goto(`/timeline/${RND}?metric=%3Cscript%3E&mode=zoom`);
    await expect(page.getByText("Unsupported values for: metric, mode.")).toBeVisible();
    await expect(page.locator("main")).not.toContainText("<script>");
  });
});

test.describe("Universe Compare", () => {
  test("shows KPIs, waterfalls and distributions of paired differences", async ({ page }) => {
    await page.goto(`/compare/${RND}`);
    await expect(
      page.getByRole("region", { name: /medians with p10 to p90 at FY2025 Q3/ }),
    ).toBeVisible();
    await expect(page.getByRole("figure", { name: /From baseline to/ })).toHaveCount(2);
    await expect(page.getByRole("figure", { name: /minus baseline/ })).toHaveCount(4);
    await expect(page.getByText(/means add up, medians do not/).first()).toBeVisible();
    await expect(page.getByText(/under the mock model, not validated/).first()).toBeVisible();
    await saveScreen(page, `compare-${test.info().project.name}`);
    await page
      .getByRole("figure", { name: /From baseline to/ })
      .first()
      .scrollIntoViewIfNeeded();
    await saveScreen(page, `compare-waterfall-${test.info().project.name}`);
    await page
      .getByRole("figure", { name: /minus baseline/ })
      .first()
      .scrollIntoViewIfNeeded();
    await saveScreen(page, `compare-distribution-${test.info().project.name}`);
  });

  test("compares results on the same footing", async ({ page }) => {
    await page.goto(`/compare/${RND}`);
    await page.getByRole("combobox", { name: "Other result" }).selectOption(CAPEX);
    await page.getByRole("button", { name: "Compare", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`with=${CAPEX}`));
    await expect(page.getByText("Comparable")).toBeVisible();
    await expect(page.getByText(/both baselines are the same paths/)).toBeVisible();
  });

  test("blocks a comparison across different cutoffs (FC-09)", async ({ page }) => {
    await page.goto(`/compare/${RND}?with=${WORKFORCE}`);
    await expect(page.getByText("Comparison blocked")).toBeVisible();
    await expect(
      page.getByText("The results have different knowledge cutoffs (2022-12-31 and 2022-06-30)."),
    ).toBeVisible();
    await page.getByText("Comparison blocked").scrollIntoViewIfNeeded();
    await saveScreen(page, `compare-blocked-${test.info().project.name}`);
  });
});
