import { expect, test, type Page } from "@playwright/test";

const SHA = "ab".repeat(32);
const now = new Date().toISOString();
const XSS = `<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>`;
const PAGES = ["/", "/universe", "/models", "/launch", "/valuation", "/risk", "/methodology"];

function hostileJob(): Record<string, unknown> {
  return {
    job_id: "job-0123456789ab",
    request: {
      kind: "training",
      idempotency_key: "stage-24-test-run",
      owner: "owner",
      model: "gru_attention",
      params: [],
      dataset_id: `fds-20261028-${"ab".repeat(6)}`,
      dataset_sha256: SHA,
      protocol_path: "data/protocols/stage-16-temporal-large.json",
      fold_year: 2026,
      seed: 1,
      device: "cuda",
      max_epochs: 80,
      max_runtime_seconds: 600,
      spend_limit_usd: 0,
      rate_usd_per_hour: 0,
      overnight: false,
    },
    estimate: { seconds: 35, vram_mb: 225, disk_mb: 3, cost_usd: 0, basis: XSS },
    status: "failed",
    approved_by: "owner",
    approved_at: now,
    attempt: 1,
    max_attempts: 3,
    epoch: 2,
    best_epoch: 2,
    best_validation_loss: 0.84,
    train_loss: 0.9,
    validation_loss: 0.85,
    batch_size: 256,
    progress_percent: 25,
    elapsed_seconds: 42,
    spent_usd: 0,
    last_heartbeat: now,
    worker: XSS,
    reason: XSS,
    alerts: [XSS],
    checkpoint_sha256: SHA,
    created_at: now,
    updated_at: now,
  };
}

async function watchPolicy(page: Page): Promise<string[]> {
  const found: string[] = [];
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) found.push(message.text());
  });
  return found;
}

test.describe("Headers of the app", () => {
  test("every page answers with its protective headers", async ({ request }) => {
    for (const path of PAGES) {
      const headers = (await request.get(path)).headers();
      expect(headers["content-security-policy"], path).toContain("frame-ancestors 'none'");
      expect(headers["x-content-type-options"], path).toBe("nosniff");
      expect(headers["x-frame-options"], path).toBe("DENY");
      expect(headers["referrer-policy"], path).toBe("strict-origin-when-cross-origin");
      expect(headers["x-powered-by"], path).toBeUndefined();
    }
  });

  test("the policy breaks nothing the app does", async ({ page }) => {
    const violations = await watchPolicy(page);
    await page.route("**/api/v1/**", (route) => route.fulfill({ json: [] }));
    for (const path of PAGES) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
    }
    expect(violations).toEqual([]);
  });

  test("the policy stops a script added to the page", async ({ page }) => {
    const violations = await watchPolicy(page);
    await page.goto("/");
    await page.evaluate(() => {
      const script = document.createElement("script");
      script.src = "https://evil.example/x.js";
      document.head.append(script);
    });
    await expect.poll(() => violations.length).toBeGreaterThan(0);
  });
});

test.describe("Untrusted text from the job service", () => {
  test("stays text", async ({ page }) => {
    await page.route("**/api/v1/jobs**", async (route) => {
      const url = route.request().url();
      await route.fulfill({
        json: url.includes("/logs")
          ? [{ seq: 1, at: now, level: "error", message: XSS }]
          : [hostileJob()],
      });
    });
    await page.goto("/models");
    await expect(page.getByText(XSS).first()).toBeVisible();
    await page.getByText("Log", { exact: true }).click();
    await expect(page.getByText(XSS).first()).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBe(
      undefined,
    );
    await expect(page.locator('img[src="x"]')).toHaveCount(0);
  });
});

test.describe("Notices", () => {
  test("the FRED notice and its terms are on the methodology page", async ({ page }) => {
    await page.goto("/methodology");
    await expect(page.getByRole("heading", { name: "Source notices" })).toBeVisible();
    await expect(
      page.getByText(/not endorsed or certified by the Federal Reserve Bank/).first(),
    ).toBeVisible();
    const terms = page.getByRole("link", { name: "FRED terms of use" });
    await expect(terms).toHaveAttribute("href", "https://fred.stlouisfed.org/legal/");
  });

  test("the data catalog shows the open blocks of FRED", async ({ page }) => {
    await page.goto("/data-catalog/fred-alfred");
    await expect(page.getByRole("heading", { name: "Blocked by the terms" })).toBeVisible();
    await expect(page.getByText("Machine learning", { exact: true })).toBeVisible();
    await expect(page.getByText("Archive", { exact: true })).toBeVisible();
    await expect(page.getByText("Republication", { exact: true })).toBeVisible();
  });
});
