import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const REQUEST = {
  kind: "simulation",
  idempotency_key: "launch-1000-20261106",
  owner: "owner",
  case_id: "case-48898-20251231",
  decision: {},
  settings: { paths: 1000, seed: 20261106, batch_paths: 250 },
  max_runtime_seconds: 900,
};

function job(status: string, percent: number) {
  return {
    job_id: "job-0123456789ab",
    request: REQUEST,
    status,
    approved_at: status === "queued" ? null : "2026-11-06T10:00:00Z",
    progress_percent: percent,
    elapsed_seconds: 12,
    reason: null,
  };
}

async function serve(page: Page, jobs: unknown[]) {
  await page.route("**/api/v1/**", (route) => {
    const url = route.request().url();
    if (url.endsWith("/simulations/estimate")) {
      return route.fulfill({
        json: { seconds: 5.5, vram_mb: 0, disk_mb: 2.8, cost_usd: 0, basis: "0.0055 s per path" },
      });
    }
    if (url.endsWith("/simulations")) return route.fulfill({ status: 201, json: job("queued", 0) });
    return route.fulfill({ json: jobs });
  });
}

test.describe("Launch Center", () => {
  test("says the run is conditional before any number", async ({ page }) => {
    await page.goto("/launch");
    await expect(page.getByRole("heading", { level: 1, name: "Launch Center" })).toBeVisible();
    const warning = page.getByText("Conditional on the assumed model, not validated").first();
    await expect(warning).toBeVisible();
    const main = page.locator("main");
    await expect(main).toContainText("not confidence intervals");
    await expect(main).toContainText("no causal effect has been estimated");
    await expect(main).toContainText("not a plan of");
    const first = await warning.boundingBox();
    const numbers = await page.getByRole("heading", { name: "Paths", exact: true }).boundingBox();
    expect(first?.y ?? 0).toBeLessThan(numbers?.y ?? 0);
    await expect(page.getByText("Hypothetical decision")).toBeVisible();
  });

  test("shows how each input is known", async ({ page }) => {
    await page.goto("/launch");
    await page.getByText("How each input is known").click();
    await expect(page.getByRole("cell", { name: "Implied" }).first()).toBeVisible();
    await expect(page.getByRole("cell", { name: "Assumed" }).first()).toBeVisible();
    await expect(page.getByText(/the warehouse holds no working capital/)).toBeVisible();
  });

  test("draws the paths with a real label, not a mock one", async ({ page }) => {
    await page.goto("/launch");
    const paths = page.getByRole("region", { name: "Paths", exact: true });
    const paired = page.getByRole("region", { name: "Paired change" });
    await expect(paths.locator("svg").first()).toBeVisible();
    await expect(paired.getByText(/under the assumed model/)).toBeVisible();
    await expect(page.getByRole("main").getByText(/mock/i)).toHaveCount(0);
  });

  test("shows risks with their error, and zero as a bound", async ({ page }) => {
    await page.goto("/launch");
    const risks = page.getByRole("region", { name: "Risks" });
    await expect(
      risks
        .getByText(/None seen, below/)
        .locator("visible=true")
        .first(),
    ).toBeVisible();
    await expect(risks.getByText(/±/).locator("visible=true").first()).toBeVisible();
    await expect(risks.getByText(/Monte Carlo error only/)).toBeVisible();
  });

  test("shows convergence at every size and the worst paths", async ({ page }) => {
    await page.goto("/launch");
    const convergence = page.getByRole("region", { name: "Convergence" }).first();
    for (const size of ["500 paths", "1000 paths", "3000 paths", "10000 paths"]) {
      await expect(convergence.getByRole("columnheader", { name: size })).toBeVisible();
    }
    const tails = page.getByRole("region", { name: "Worst paths" });
    await expect(
      tails
        .getByText(/[+-]\d+\.\d+ points/)
        .locator("visible=true")
        .first(),
    ).toBeVisible();
  });

  test("says when no service is running", async ({ page }) => {
    await page.route("**/api/v1/**", (route) => route.abort());
    await page.goto("/launch");
    await expect(page.getByText("The service is not running")).toBeVisible();
  });

  test("asks for an estimate before a run can be queued", async ({ page }) => {
    await serve(page, []);
    await page.goto("/launch");
    await expect(page.getByRole("button", { name: "Queue this run" })).toHaveCount(0);
    await page.getByRole("button", { name: "Estimate" }).click();
    await expect(page.getByText(/0.0055 s per path/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Queue this run" })).toBeVisible();
  });

  test("shows the progress of a run and how to stop it", async ({ page }) => {
    await serve(page, [job("running", 40)]);
    await page.goto("/launch");
    const bar = page.getByRole("progressbar", { name: /Progress of run/ });
    await expect(bar).toHaveAttribute("aria-valuenow", "40");
    await expect(page.getByRole("button", { name: "Stop after checkpoint" })).toBeVisible();
  });

  test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
    await serve(page, [job("running", 40)]);
    await page.goto("/launch");
    await page.getByRole("progressbar", { name: /Progress of run/ }).waitFor();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
