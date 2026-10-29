import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { SECTIONS } from "../src/navigation/sections";

/*
 * Gate A (Stage 08): the cross-cutting checks of docs/stages/08-frontend-test-gate.md.
 * Each test names the test case it covers (TC-xx). Feature behaviour stays in the
 * feature specs; this file checks every route and the journeys that join the features.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const fixture = (path: string) =>
  JSON.parse(
    readFileSync(
      fileURLToPath(new URL(`../../../packages/contracts/fixtures/${path}`, import.meta.url)),
      "utf8",
    ),
  ) as unknown;

const COMPANIES = (fixture("demo/companies.json") as { company: { company_id: string } }[]).map(
  (dossier) => dossier.company.company_id,
);
const RESULTS = (fixture("mock/results.json") as { result_id: string }[]).map(
  (result) => result.result_id,
);
const NOTEBOOK_TEXT = JSON.stringify(fixture("notebook/valid-export.json"));
const NORTHWIND = "5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13";
const RND_RESULT = "2d7c9e41-5b3a-4f6e-8c1d-9a0b7e6f5c34";

const ROUTES = [
  ...SECTIONS.map((section) => section.href),
  "/design-system",
  ...COMPANIES.map((id) => `/dossier/${id}`),
  ...COMPANIES.map((id) => `/decisions?company=${id}`),
  ...RESULTS.map((id) => `/timeline/${id}`),
  ...RESULTS.map((id) => `/compare/${id}`),
];

/** Errors a visitor would never see but that signal a broken page (TC-16). */
function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message.slice(0, 160)}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text().slice(0, 160)}`);
  });
  return errors;
}

async function seedNotebook(page: Page): Promise<void> {
  await page.addInitScript((value) => {
    if (!sessionStorage.getItem("seeded")) {
      localStorage.setItem("multiverse.notebook", value);
      sessionStorage.setItem("seeded", "1");
    }
  }, NOTEBOOK_TEXT);
}

test.describe("every route (TC-06, TC-09, TC-14, TC-16, TC-18, TC-19)", () => {
  for (const route of ROUTES) {
    test(`checks ${route}`, async ({ page }) => {
      const errors = watchErrors(page);
      await page.emulateMedia({ reducedMotion: "reduce" });
      const response = await page.goto(route);
      expect(response?.status(), "HTTP status").toBe(200);
      await page.waitForLoadState("networkidle");

      expect(errors, "console and page errors").toEqual([]);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, "horizontal overflow in px").toBeLessThanOrEqual(0);
      await expect(page.locator("h1")).toHaveCount(1);

      // The prototype badge is in the top bar of every page (SYN-01).
      await expect(
        page
          .getByRole("banner")
          .getByText(/^Prototype/)
          .filter({ visible: true }),
      ).toBeVisible();

      const text = await page.locator("main").innerText();
      // Pages that show figures say on the page itself that they are invented (SYN-01).
      if (/^\/(dossier\/|decisions\?|timeline\/|compare\/)/.test(route)) {
        expect(text, "synthetic or mock label").toMatch(/\b(Synthetic|Mock|Demo)\b/);
      }
      // FP-04: no claim of accuracy or proof; the only mentions are disclaimers.
      const claims = text
        .split(/(?<=[.!?])\s+/)
        .filter((sentence) => /\b(accurate|accuracy|proven|proves)\b/i.test(sentence))
        .filter((sentence) => !/^That |not|never|does not|Prediction and cause/i.test(sentence));
      expect(claims, "accuracy or proof claims").toEqual([]);
      // No promise of a stage that is already built (Stages 03 to 08).
      expect(text, "stale stage promise").not.toMatch(
        /(arrives in|planned for|planned with|In progress,) Stage 0[3-8]\b/i,
      );

      const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
      expect(
        results.violations.map((violation) => `${violation.id}: ${violation.nodes.length}`),
      ).toEqual([]);
    });
  }

  test("checks the notebook with saved scenarios", async ({ page }) => {
    const errors = watchErrors(page);
    await seedNotebook(page);
    await page.goto("/notebook?scenario=4e2f6a8c-1b3d-4f5e-9a7c-0d2e4f6a8b1c");
    await expect(page.getByRole("heading", { name: "Revisions", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });
});

test("no internal link on any route is broken (TC-15)", async ({ page, request }) => {
  test.skip(test.info().project.name !== "desktop", "Links are the same at every width");
  test.setTimeout(180_000);
  const hrefs = new Set<string>();
  await seedNotebook(page);
  for (const route of [...ROUTES, "/notebook?scenario=4e2f6a8c-1b3d-4f5e-9a7c-0d2e4f6a8b1c"]) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const found = await page
      .locator('a[href^="/"]')
      .evaluateAll((links) => links.map((link) => link.getAttribute("href") ?? ""));
    for (const href of found) hrefs.add(href.split("#")[0] || "/");
  }
  const broken: string[] = [];
  for (const href of hrefs) {
    const response = await request.get(href);
    if (response.status() !== 200) broken.push(`${response.status()} ${href}`);
  }
  expect(broken).toEqual([]);
  expect(hrefs.size).toBeGreaterThan(40);
});

test("the whole journey works: search, cutoff, decision, mock run, comparison, save, export (TC-01)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("/universe");
  await page.getByRole("searchbox", { name: "Search" }).fill("nwsc");
  await page.getByRole("link", { name: "Northwind Semiconductors Inc." }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Northwind Semiconductors Inc." }),
  ).toBeVisible();

  await page.getByRole("combobox", { name: "Known as of" }).selectOption("2022-12-31");
  await page.getByRole("button", { name: "Show", exact: true }).click();
  await expect(page).toHaveURL(/asOf=2022-12-31/);
  await page.getByRole("link", { name: "Build a decision for this company" }).click();
  await expect(page.getByRole("combobox", { name: "Known as of" })).toHaveValue("2022-12-31");

  await page
    .getByRole("combobox", { name: /Measured against/ })
    .selectOption("fraction_of_previous_rnd_budget");
  await page.getByRole("textbox", { name: /^R&D change/ }).fill("40");
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(page.getByTestId("validation-status")).toContainText("No blocking errors");

  await page.getByRole("button", { name: "Run", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Ready to run" });
  await expect(dialog.getByLabel("Scenario JSON")).toContainText('"value": "0.4"');
  await dialog.getByRole("link", { name: "Timeline Explorer" }).click();
  await page.getByRole("link", { name: "Northwind R&D budget +20% and +40%" }).click();
  await expect(page.getByTestId("timeline-svg")).toBeVisible();
  await page.getByRole("link", { name: "Compare these scenarios" }).click();
  await expect(page.getByRole("figure", { name: /From baseline to R&D \+40%/ })).toBeVisible();

  await page.goBack();
  await page.goBack();
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1, name: "Decision Builder" })).toBeVisible();
  await page
    .getByRole("combobox", { name: /Measured against/ })
    .selectOption("fraction_of_previous_rnd_budget");
  await page.getByRole("textbox", { name: /^R&D change/ }).fill("40");
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await page.getByRole("button", { name: "Save to notebook" }).click();
  await page
    .getByRole("dialog", { name: "Save to notebook" })
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await page.getByRole("link", { name: "Open in notebook" }).click();
  await expect(page).toHaveURL(/\/notebook\?scenario=/);

  const download = page.waitForEvent("download");
  await page.getByTestId("revision-1").getByRole("button", { name: "Export report" }).click();
  expect((await download).suggestedFilename()).toMatch(/_r1_DEMO\.md$/);
  await expect(page.getByTestId("report-row")).toHaveCount(1);
  expect(errors).toEqual([]);
});

test.describe("keyboard only (TC-05)", () => {
  async function tabTo(page: Page, name: RegExp, limit = 250): Promise<void> {
    for (let i = 0; i < limit; i += 1) {
      await page.keyboard.press("Tab");
      const label = await page.evaluate(() => {
        const element = document.activeElement as HTMLElement | null;
        return element
          ? `${element.getAttribute("aria-label") ?? ""} ${element.textContent ?? ""}`.trim()
          : "";
      });
      if (name.test(label)) return;
    }
    throw new Error(`Tab never reached ${name}`);
  }

  test("validates, opens Run and returns focus without a mouse", async ({ page }) => {
    await page.goto(`/decisions?company=${NORTHWIND}&type=capex_expansion`);
    await tabTo(page, /^Validate$/);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Validation", level: 2 })).toBeFocused();
    await tabTo(page, /^Run$/);
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Ready to run" });
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeFocused();
  });

  test("reaches and reads the timeline chart without a mouse", async ({ page }) => {
    await page.goto(`/timeline/${RND_RESULT}`);
    const chart = page.getByRole("group", { name: /Revenue/ });
    for (
      let i = 0;
      i < 120 && !(await chart.evaluate((element) => element === document.activeElement));
      i += 1
    ) {
      await page.keyboard.press("Tab");
    }
    await expect(chart).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByTestId("chart-tooltip")).toBeVisible();
  });

  test("shows a visible focus ring on every kind of control (TC-07)", async ({ page }) => {
    await page.goto(`/decisions?company=${NORTHWIND}&type=acquisition`);
    const ring = async () =>
      page.evaluate(() => {
        const element = document.activeElement as HTMLElement;
        const target =
          element.closest("label") && element.matches("input[type=radio], input.sr-only")
            ? (element.closest("label") as HTMLElement)
            : element;
        const style = getComputedStyle(target);
        return {
          style: style.outlineStyle,
          width: parseFloat(style.outlineWidth),
          shadow: style.boxShadow,
        };
      });
    const checked: string[] = [];
    for (let i = 0; i < 40; i += 1) {
      await page.keyboard.press("Tab");
      const role = await page.evaluate(() => {
        const element = document.activeElement as HTMLElement;
        // The calendar button inside a date field is a browser part with its own ring.
        if (element.matches("input[type=date]:not(:focus-visible)")) return "date-picker";
        return `${element.tagName.toLowerCase()}${element.getAttribute("type") ? `[${element.getAttribute("type")}]` : ""}`;
      });
      if (role === "date-picker") continue;
      const focus = await ring();
      const visible = (focus.style !== "none" && focus.width >= 2) || focus.shadow !== "none";
      expect(visible, `focus ring on ${role}`).toBe(true);
      checked.push(role);
    }
    expect(new Set(checked).size).toBeGreaterThanOrEqual(4);
  });
});

test("motion stops with reduced motion (TC-08)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const route of ["/", `/timeline/${RND_RESULT}`, `/decisions?company=${NORTHWIND}`]) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const running = await page.evaluate(
      () =>
        document.getAnimations().filter((animation) => animation.playState === "running").length,
    );
    expect(running, route).toBe(0);
  }
});

test.describe("refresh keeps the state (TC-10)", () => {
  test("in the Decision Builder", async ({ page }) => {
    await page.goto(`/decisions?company=${NORTHWIND}`);
    await page.getByRole("radio", { name: /Divestiture/ }).check();
    await page.getByRole("combobox", { name: "Known as of" }).selectOption("2022-06-30");
    await page.reload();
    await expect(page.getByRole("radio", { name: /Divestiture/ })).toBeChecked();
    await expect(page.getByRole("combobox", { name: "Known as of" })).toHaveValue("2022-06-30");
  });

  test("in the Timeline Explorer", async ({ page }) => {
    await page.goto(`/timeline/${RND_RESULT}`);
    await page.getByText("EBITDA (calculated)", { exact: true }).click();
    await page.getByText("Change vs baseline").click();
    await page.reload();
    await expect(page.getByRole("radio", { name: "EBITDA (calculated)" })).toBeChecked();
    await expect(page.getByRole("radio", { name: "Change vs baseline" })).toBeChecked();
  });
});

test("converts typed units exactly into the scenario (TC-12)", async ({ page }) => {
  await page.goto(`/decisions?company=${NORTHWIND}&type=acquisition`);
  await page.getByRole("textbox", { name: /^Purchase price/ }).fill("1500");
  await page.getByRole("textbox", { name: "Deal costs" }).fill("2.5");
  await page.getByRole("textbox", { name: "Cash on hand" }).fill("60");
  await page.getByRole("textbox", { name: "New debt", exact: true }).fill("40");
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const json = page.getByRole("dialog", { name: "Ready to run" }).getByLabel("Scenario JSON");
  await expect(json).toContainText('"value": "1500000000"');
  await expect(json).toContainText('"deal_cost_fraction": "0.025"');
  await expect(json).toContainText('"cash": "0.6"');
});

test("the builder uses exactly the figures the dossier shows (TC-17)", async ({ page }) => {
  type Value = {
    metric: string;
    quantity: { value: string } | null;
    period: { type: string; end_date: string };
  };
  const dossier = (
    fixture("demo/companies.json") as { company: { company_id: string }; values: Value[] }[]
  ).find((item) => item.company.company_id === NORTHWIND);
  // Public by 2022-12-31: FY2021 Q4 to FY2022 Q3 (FY2022 Q4 was filed later).
  const window = ["2021-12-31", "2022-03-31", "2022-06-30", "2022-09-30"];
  const rnd = (dossier?.values ?? [])
    .filter((value) => value.metric === "rnd_expense" && window.includes(value.period.end_date))
    .reduce((sum, value) => sum + Number(value.quantity?.value ?? 0), 0);
  const expected = `USD ${(rnd / 1e6).toFixed(1)}m`;

  await page.goto(`/decisions?company=${NORTHWIND}&type=rnd_change`);
  await page
    .getByRole("combobox", { name: /Measured against/ })
    .selectOption("fraction_of_previous_rnd_budget");
  await page.getByRole("textbox", { name: /^R&D change/ }).fill("40");
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(
    page.getByText(`Previous R&D budget: ${expected}, trailing four quarters`),
  ).toBeVisible();

  const revenue = (dossier?.values ?? []).find(
    (value) => value.metric === "revenue" && value.period.end_date === "2022-09-30",
  );
  await page.goto(`/timeline/${RND_RESULT}`);
  await page.getByRole("button", { name: "Show as table" }).click();
  const row = page
    .getByRole("region", { name: /every plotted point/ })
    .getByRole("row", { name: /FY2022 Q3/ });
  await expect(row).toContainText(`USD ${(Number(revenue?.quantity?.value) / 1e9).toFixed(1)}bn`);
});
