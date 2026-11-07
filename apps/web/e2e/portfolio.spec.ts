import { mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";

/*
 * Screenshots of the portfolio (Stage 25), on request only:
 *   SAVE_PORTFOLIO=1 npx playwright test portfolio --project=desktop
 * The engine is played by fixtures: a case study report and the Stage 22 run.
 */

test.skip(!process.env["SAVE_PORTFOLIO"], "Set SAVE_PORTFOLIO=1 to take the screenshots");

const OUT = fileURLToPath(new URL("../../../docs/portfolio/screens/", import.meta.url));
const NVIDIA = "f1bad442-6a6f-572e-a9d8-5b4109e7e757";
const JOB = "job-0123456789ab";
const DOCUMENT: unknown = JSON.parse(
  readFileSync(
    new URL("../../../docs/case-studies/rnd-allocation/rnd-up/document.json", import.meta.url),
    "utf8",
  ),
);
const RUN: unknown = JSON.parse(
  readFileSync(
    new URL("../../../data/simulation/report-48898-acquisition.json", import.meta.url),
    "utf8",
  ),
);

async function engine(page: Page) {
  await page.route("**/api/v1/**", (route) => {
    const url = route.request().url();
    if (url.endsWith("/report/document")) return route.fulfill({ json: DOCUMENT });
    if (url.endsWith("/report")) return route.fulfill({ json: RUN });
    return route.fulfill({
      json: [
        {
          job_id: JOB,
          status: "completed",
          request: {
            kind: "simulation",
            case_id: "case-50863-20261106",
            decision: { type: "rnd_change" },
            settings: { paths: 3000 },
          },
          progress_percent: 100,
          elapsed_seconds: 62,
          reason: null,
        },
      ],
    });
  });
}

async function shoot(page: Page, name: string) {
  mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: `${OUT}${name}.png` });
}

test("screens of the portfolio", async ({ page }) => {
  test.setTimeout(120_000);
  await engine(page);
  await page.goto("/universe");
  await expect(page.getByRole("heading", { level: 3 }).first()).toContainText("NVIDIA");
  await shoot(page, "01-universe");

  await page.goto(`/dossier/${NVIDIA}`);
  await page.getByText("Research forecast, not approved for the product").scrollIntoViewIfNeeded();
  await shoot(page, "02-dossier-forecast");

  await page.goto(`/decisions?company=${NVIDIA}&type=rnd_change`);
  await page.getByRole("textbox", { name: /^R&D change/ }).fill("20");
  await page
    .getByRole("combobox", { name: /Measured against/ })
    .selectOption({ label: "% of the previous R&D budget" });
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ready to run" })).toBeVisible();
  await shoot(page, "03-run-dialog");

  await page.goto(`/run?job=${JOB}`);
  await expect(page.getByRole("heading", { name: "Paths" })).toBeVisible();
  await shoot(page, "04-run-result");

  await page.goto(`/reports?job=${JOB}`);
  await expect(page.getByRole("heading", { name: "Sources" })).toBeAttached();
  await shoot(page, "05-report-studio");

  await page.goto("/models");
  await page.getByRole("heading", { name: "Forecast of real companies" }).scrollIntoViewIfNeeded();
  await shoot(page, "06-models");
});
