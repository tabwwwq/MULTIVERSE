import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

const RUN = new URL("../../../docs/case-studies/rnd-allocation/rnd-up/", import.meta.url);
const DOCUMENT = JSON.parse(readFileSync(new URL("document.json", RUN), "utf8")) as {
  report_doc_id: string;
  claims: { claim_id: string; value: string }[];
  sources: { ref_id: string; kind: string; target: string }[];
};
const MARKDOWN = readFileSync(new URL("report.md", RUN));
const CSV = readFileSync(new URL("report.csv", RUN));
const JOB = "job-0123456789ab";
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

function attachment(body: Buffer, type: string, name: string) {
  return {
    status: 200,
    body,
    headers: {
      "content-type": type,
      "content-disposition": `attachment; filename="${name}"`,
      "access-control-allow-origin": "*",
      "access-control-expose-headers": "content-disposition",
    },
  };
}

async function engine(page: Page) {
  await page.route("**/api/v1/**", (route) => {
    const url = route.request().url();
    if (url.endsWith("/report/document")) return route.fulfill({ json: DOCUMENT });
    if (url.endsWith("/report/markdown")) {
      return route.fulfill(attachment(MARKDOWN, "text/markdown", `${DOCUMENT.report_doc_id}.md`));
    }
    if (url.endsWith("/report/csv")) {
      return route.fulfill(attachment(CSV, "text/csv", `${DOCUMENT.report_doc_id}.csv`));
    }
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

test.describe("Report Studio", () => {
  test("lists the runs of this computer and opens a report", async ({ page }) => {
    await engine(page);
    await page.goto("/reports");
    await expect(page.getByRole("heading", { level: 1, name: "Report Studio" })).toBeVisible();
    await page.getByRole("link", { name: `Report of ${JOB}` }).click();
    await expect(page).toHaveURL(new RegExp(`/reports\\?job=${JOB}$`));
    await expect(page.getByRole("heading", { level: 2 })).toContainText("INTEL CORP");
    await expect(page.getByText(/^Conditional on the assumed model, not validated/)).toBeVisible();
    await expect(page.getByRole("heading", { level: 3 })).toHaveCount(12);
    await expect(page.getByText(DOCUMENT.report_doc_id)).toBeVisible();
  });

  test("links each number to its claim and each claim to its sources", async ({ page }) => {
    await engine(page);
    await page.goto(`/reports?job=${JOB}`);
    const claim = DOCUMENT.claims.find((item) => item.claim_id === "C10");
    await page.getByRole("link", { name: "Claim C10" }).first().click();
    await expect(page).toHaveURL(/#claim-C10$/);
    await expect(page.locator("#claim-C10")).toContainText(claim?.value ?? "missing");
    const filing = DOCUMENT.sources.find((ref) => ref.kind === "sec_filing");
    const link = page.locator(`#source-${filing?.ref_id ?? "S0"}`).getByRole("link");
    await expect(link).toHaveAttribute("href", filing?.target ?? "missing");
    await expect(link).toHaveAttribute("rel", /noopener/);
  });

  test("downloads the Markdown and the CSV exactly as stored", async ({ page }) => {
    await engine(page);
    await page.goto(`/reports?job=${JOB}`);
    for (const [label, body, suffix] of [
      ["Markdown", MARKDOWN, "md"],
      ["CSV", CSV, "csv"],
    ] as const) {
      const waiting = page.waitForEvent("download");
      await page.getByRole("link", { name: label, exact: true }).click();
      const download = await waiting;
      expect(download.suggestedFilename()).toBe(`${DOCUMENT.report_doc_id}.${suffix}`);
      const path = await download.path();
      expect(readFileSync(path).equals(body)).toBe(true);
    }
  });

  test("prints as a document without the navigation", async ({ page }, info) => {
    await engine(page);
    await page.goto(`/reports?job=${JOB}`);
    await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
    await page.emulateMedia({ media: "print" });
    await expect(page.getByRole("button", { name: "Print or save as PDF" })).toBeHidden();
    await expect(page.getByRole("banner").first()).toBeHidden();
    await expect(page.getByRole("heading", { name: "Claims" })).toBeVisible();
    if (info.project.name === "desktop") {
      const pdf = await page.pdf({ format: "A4" });
      expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
      expect(pdf.length).toBeGreaterThan(20_000);
    }
  });

  test("says how to start the engine when it is off", async ({ page }) => {
    await page.route("**/api/v1/**", (route) => route.abort());
    await page.goto("/reports");
    await expect(page.getByText("Reports live with the engine on this computer")).toBeVisible();
    await page.goto(`/reports?job=${JOB}`);
    await expect(page.getByText("This report cannot be read")).toBeVisible();
  });

  test("ignores a job that is not a job id", async ({ page }) => {
    await engine(page);
    await page.goto("/reports?job=..%2F..%2Fsecret");
    await expect(page.getByRole("link", { name: `Report of ${JOB}` })).toBeVisible();
  });

  test("has no WCAG 2.2 A or AA violations on a report", async ({ page }) => {
    await engine(page);
    await page.goto(`/reports?job=${JOB}`);
    await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });

  test("fits a phone without sideways scrolling", async ({ page }, info) => {
    test.skip(info.project.name !== "mobile", "phone layout only");
    await engine(page);
    await page.goto(`/reports?job=${JOB}`);
    await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
