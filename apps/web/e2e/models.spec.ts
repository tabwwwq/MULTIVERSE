import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const SHA = "ab".repeat(32);
const now = new Date().toISOString();

function job(changes: Record<string, unknown>): Record<string, unknown> {
  return {
    job_id: "job-0123456789ab",
    request: {
      idempotency_key: "stage-18-test-run",
      owner: "owner",
      model: "gru_attention",
      params: [],
      dataset_id: `fds-20261028-${"ab".repeat(6)}`,
      dataset_sha256: SHA,
      protocol_path: "protocol.json",
      fold_year: 2026,
      seed: 1,
      device: "cuda",
      max_epochs: 80,
      max_runtime_seconds: 600,
      spend_limit_usd: 0,
      rate_usd_per_hour: 0,
      overnight: false,
    },
    estimate: {
      seconds: 35,
      vram_mb: 225,
      disk_mb: 3,
      cost_usd: 0,
      basis: "0.65 s per epoch per 10 000 rows on cuda",
    },
    status: "running",
    approved_by: "owner",
    approved_at: now,
    attempt: 1,
    max_attempts: 3,
    epoch: 20,
    best_epoch: 18,
    best_validation_loss: 0.84,
    train_loss: 0.9,
    validation_loss: 0.85,
    batch_size: 256,
    progress_percent: 25,
    elapsed_seconds: 42,
    spent_usd: 0,
    last_heartbeat: now,
    worker: "laptop-1",
    reason: null,
    alerts: [],
    checkpoint_sha256: SHA,
    created_at: now,
    updated_at: now,
    ...changes,
  };
}

async function serve(page: Page, jobs: unknown[]): Promise<string[]> {
  const posts: string[] = [];
  await page.route("**/api/v1/jobs**", async (route: Route) => {
    const request = route.request();
    if (request.method() === "POST") {
      posts.push(new URL(request.url()).pathname);
      await route.fulfill({ json: jobs[0] });
    } else if (request.url().includes("/logs")) {
      await route.fulfill({
        json: [{ seq: 1, at: now, level: "info", message: "epoch 20: train 0.9000" }],
      });
    } else {
      await route.fulfill({ json: jobs });
    }
  });
  return posts;
}

test.describe("Model Observatory", () => {
  test("says so when the job service is not running", async ({ page }) => {
    await page.route("**/api/v1/jobs**", (route) => route.abort());
    await page.goto("/models");
    await expect(page.getByText("The job service is not running")).toBeVisible();
    await expect(page.getByText("Not approved for the product", { exact: true })).toBeVisible();
  });

  test("shows the progress of a running job from 0 to 100", async ({ page }) => {
    const posts = await serve(page, [job({})]);
    await page.goto("/models");
    const bar = page.getByRole("progressbar");
    await expect(bar).toHaveAttribute("aria-valuenow", "25");
    await expect(page.getByText("25%", { exact: true })).toBeVisible();
    await expect(page.getByText("20 of 80")).toBeVisible();
    await page.getByRole("button", { name: "Stop after checkpoint" }).click();
    await expect.poll(() => posts).toEqual(["/api/v1/jobs/job-0123456789ab/stop"]);
    await page.getByText("Log", { exact: true }).click();
    await expect(page.getByText("epoch 20: train 0.9000")).toBeVisible();
  });

  test("asks for approval with the estimate first", async ({ page }) => {
    const posts = await serve(page, [
      job({ status: "queued", approved_by: null, approved_at: null, attempt: 0, epoch: 0 }),
    ]);
    await page.goto("/models");
    await expect(page.getByText("Waiting for approval")).toBeVisible();
    await expect(page.getByText(/225 MB of GPU memory/)).toBeVisible();
    await page.getByRole("button", { name: "Approve estimate" }).click();
    await expect.poll(() => posts).toEqual(["/api/v1/jobs/job-0123456789ab/approve"]);
  });

  test("warns about a silent worker and shows alerts of a failed job", async ({ page }) => {
    const old = new Date(Date.now() - 5 * 60_000).toISOString();
    await serve(page, [
      job({ last_heartbeat: old }),
      job({
        job_id: "job-ba9876543210",
        status: "failed",
        reason: "not a number: loss is not finite at epoch 7",
        alerts: ["not a number: loss is not finite at epoch 7"],
      }),
    ]);
    await page.goto("/models");
    await expect(page.getByText(/No heartbeat for/)).toBeVisible();
    await expect(page.getByText("Failed", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  });

  test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
    await serve(page, [job({}), job({ job_id: "job-ba9876543210", status: "paused" })]);
    await page.goto("/models");
    await expect(page.getByRole("progressbar").first()).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
