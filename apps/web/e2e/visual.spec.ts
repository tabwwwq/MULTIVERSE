import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

const NVIDIA = "f1bad442-6a6f-572e-a9d8-5b4109e7e757";
const NORTHWIND = "5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13";
const JOB = "job-0123456789ab";
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const REPORT: unknown = JSON.parse(
  readFileSync(
    new URL("../../../data/simulation/report-48898-acquisition.json", import.meta.url),
    "utf8",
  ),
);

function run(job: string, status: string, percent: number, createdAt: string) {
  return {
    job_id: job,
    status,
    created_at: createdAt,
    approved_at: "2026-11-07T10:00:00Z",
    progress_percent: percent,
    elapsed_seconds: 12,
    last_heartbeat: new Date().toISOString(),
    reason: null,
    request: {
      kind: "simulation",
      case_id: "case-1045810-20261106",
      decision: { type: "rnd_change" },
      settings: { paths: 1000 },
    },
  };
}

async function engine(page: Page) {
  await page.route("**/api/v1/**", (route) => {
    const url = route.request().url();
    if (url.endsWith("/report")) return route.fulfill({ json: REPORT });
    return route.fulfill({
      json: [
        run(JOB, "completed", 100, "2026-11-07T10:00:00Z"),
        run("job-abcdefabcdef", "running", 40, "2026-11-07T11:00:00Z"),
      ],
    });
  });
}

test.describe("Overview", () => {
  test("opens with the largest companies on file and five steps to a report", async ({ page }) => {
    await page.goto("/");
    const figure = page.getByRole("figure").filter({ hasText: "The largest companies on file" });
    await expect(figure.getByRole("listitem").first()).toContainText("NVIDIA");
    await expect(figure.getByRole("listitem")).toHaveCount(12);
    await expect(page.getByText("ready to run a decision")).toBeVisible();
    const steps = page
      .getByRole("region", { name: "From a company to a report" })
      .getByRole("listitem");
    await expect(steps).toHaveCount(5);
    await steps.nth(1).getByRole("link").click();
    await expect(page).toHaveURL(/\/time-machine$/);
  });
});

test.describe("Time Machine", () => {
  test("compares two dates of a company and draws the lag of each quarter", async ({ page }) => {
    await page.goto(`/time-machine?company=${NVIDIA}`);
    await expect(page.getByRole("heading", { level: 1, name: "Time Machine" })).toBeVisible();
    await expect(
      page.getByRole("img", { name: /^From the end of each quarter to the day it became public/ }),
    ).toBeVisible();
    await expect(
      page.getByText(/On the median quarter the filing came \d+ days after/),
    ).toBeVisible();
    await expect(page.getByRole("table")).toContainText("Revenue");
  });

  test("changes the company and the dates from the form", async ({ page }) => {
    await page.goto("/time-machine");
    await page.getByRole("combobox", { name: "Company" }).selectOption(NORTHWIND);
    await page.getByRole("button", { name: "Compare" }).click();
    await expect(page).toHaveURL(new RegExp(`company=${NORTHWIND}`));
    await expect(page.getByText("Fictional company")).toBeVisible();
    const second = page.getByRole("combobox", { name: "Second date" });
    const options = await second.locator("option").allTextContents();
    await page.getByRole("combobox", { name: "First date" }).selectOption(options.at(-1) ?? "");
    await second.selectOption(options[2] ?? "");
    await page.getByRole("button", { name: "Compare" }).click();
    await expect(page.getByText(`Not public on ${options[2]}`, { exact: true })).toBeVisible();
  });

  test("ignores dates and companies that are not in the data", async ({ page }) => {
    await page.goto("/time-machine?company=nobody&from=1999-01-01&to=<script>");
    await expect(page.getByRole("heading", { level: 1, name: "Time Machine" })).toBeVisible();
    await expect(page.locator("main")).not.toContainText("<script>");
  });

  test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
    await page.goto(`/time-machine?company=${NVIDIA}`);
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });
});

test.describe("Simulation Monitor", () => {
  test("lists runs with their company, progress and links", async ({ page }) => {
    await engine(page);
    await page.goto("/monitor");
    await expect(page.getByRole("heading", { level: 3, name: "NVIDIA CORP" })).toHaveCount(2);
    await expect(page.getByRole("progressbar", { name: `Progress of ${JOB}` })).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
    await expect(page.getByRole("link", { name: "Result" })).toHaveAttribute(
      "href",
      `/run?job=${JOB}`,
    );
    await expect(page.getByRole("button", { name: "Stop after checkpoint" })).toBeVisible();
  });

  test("says how to start the engine when it is off", async ({ page }) => {
    await page.route("**/api/v1/**", (route) => route.abort());
    await page.goto("/monitor");
    await expect(page.getByText("The engine is not running on this computer")).toBeVisible();
  });

  test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
    await engine(page);
    await page.goto("/monitor");
    await expect(page.getByRole("link", { name: "Result" })).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });
});

test.describe("Answers before charts", () => {
  test("a result opens with the change of value and of each risk", async ({ page }) => {
    await engine(page);
    await page.goto(`/run?job=${JOB}`);
    await expect(
      page.getByText("Paired change of model enterprise value, median path"),
    ).toBeVisible();
    await expect(page.getByText("Covenant breach", { exact: true })).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });

  test("a dossier opens with four key figures of the last four quarters", async ({ page }) => {
    await page.goto(`/dossier/${NVIDIA}`);
    await expect(page.getByText("Revenue, last four quarters")).toBeVisible();
    await expect(page.getByText("EBITDA margin (calculated)").first()).toBeVisible();
  });

  test("a company card shows its rank, size and what can be done with it", async ({ page }) => {
    await page.goto("/universe?q=NVDA");
    const card = page.getByRole("article").filter({ hasText: "NVIDIA CORP" });
    await expect(card.getByText("Public float, 2025-07-25")).toBeVisible();
    await expect(card.getByText("Research forecast")).toBeVisible();
    await expect(card.getByText("Ready to run")).toBeVisible();
  });
});
