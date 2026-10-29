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
const NORTHWIND = "5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13";
const EXPORT_TEXT = readFileSync(
  fileURLToPath(
    new URL("../../../packages/contracts/fixtures/notebook/valid-export.json", import.meta.url),
  ),
  "utf8",
);

/** Puts a notebook on the device before the page loads, as a returning visitor would have. */
async function seed(page: Page, text: string = EXPORT_TEXT): Promise<void> {
  await page.addInitScript((value) => {
    if (!sessionStorage.getItem("seeded")) {
      localStorage.setItem("multiverse.notebook", value);
      sessionStorage.setItem("seeded", "1");
    }
  }, text);
}

async function validRnd(page: Page, value = "40"): Promise<void> {
  await page.goto(`/decisions?company=${NORTHWIND}&type=rnd_change`);
  await page
    .getByRole("combobox", { name: /Measured against/ })
    .selectOption("fraction_of_previous_rnd_budget");
  await page.getByRole("textbox", { name: /^R&D change/ }).fill(value);
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(page.getByTestId("validation-status")).toContainText("No blocking errors");
}

function importInput(page: Page) {
  return page.locator('input[type="file"]');
}

test.describe("Research Notebook", () => {
  test("starts empty and says where data lives", async ({ page }) => {
    await page.goto("/notebook");
    await expect(page.getByTestId("device-only")).toContainText("Only on this device");
    await expect(page.getByText("No saved scenarios yet")).toBeVisible();
  });

  test("saves from the Decision Builder, survives a refresh and restores the form", async ({
    page,
  }) => {
    await validRnd(page);
    await page.getByRole("button", { name: "Save to notebook" }).click();
    const dialog = page.getByRole("dialog", { name: "Save to notebook" });
    await expect(dialog.getByText(/Only on this device/)).toBeVisible();
    await dialog.getByRole("textbox", { name: /Name/ }).fill("Northwind R&D +40%");
    await dialog.getByRole("textbox", { name: "Tags" }).fill("R&D, Northwind");
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    await expect(
      page.getByText(/Saved as revision 1 of “Northwind R&D \+40%”, on this device only/),
    ).toBeVisible();

    await page.getByRole("link", { name: "Open in notebook" }).click();
    await expect(page).toHaveURL(/\/notebook\?scenario=/);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Northwind R&D +40%", level: 2 })).toBeVisible();
    await expect(page.getByRole("button", { name: /Northwind R&D \+40%/ })).toContainText("rnd");
    await saveScreen(page, `notebook-${test.info().project.name}`);

    await page.getByRole("link", { name: "Open in Decision Builder" }).click();
    await expect(page.getByText(/Opened revision 1 of “Northwind R&D \+40%”/)).toBeVisible();
    const value = page.getByRole("textbox", { name: /^R&D change/ });
    await expect(value).toHaveValue("40");
    await value.fill("30");
    await page.getByRole("button", { name: "Validate", exact: true }).click();
    await page.getByRole("button", { name: "Save to notebook" }).click();
    await expect(
      page.getByRole("radio", { name: /Revision 2 of “Northwind R&D \+40%”/ }),
    ).toBeChecked();
    await page
      .getByRole("dialog", { name: "Save to notebook" })
      .getByRole("button", { name: "Save", exact: true })
      .click();
    await expect(page.getByText(/Saved as revision 2/)).toBeVisible();

    await page.getByRole("link", { name: "Open in notebook" }).click();
    await expect(page).toHaveURL(/\/notebook\?scenario=/);
    await expect(page.getByTestId("revision-1")).toContainText("+40% of the previous R&D budget");
    await expect(page.getByTestId("revision-2")).toContainText("+30% of the previous R&D budget");
    await expect(page.getByTestId("revision-2")).toContainText("edited from revision 1");
  });

  test("exports immutable reports and locks the revision (FR-RP-03)", async ({ page }) => {
    await seed(page);
    await page.goto("/notebook?scenario=4e2f6a8c-1b3d-4f5e-9a7c-0d2e4f6a8b1c");
    await expect(page.getByTestId("report-row")).toHaveCount(1);
    const revision = page.getByTestId("revision-2");
    const download = page.waitForEvent("download");
    await revision.getByRole("button", { name: "Export report" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/_r2_DEMO\.md$/);
    const text = readFileSync(await file.path(), "utf8");
    expect(text.split("\n")[0]).toMatch(/^> SYNTHETIC DEMO DATA/);
    expect(text).toContain('"revision": 2');
    await expect(revision.getByText("Report exported")).toBeVisible();

    await revision.getByRole("button", { name: "Export report" }).click();
    const rows = page.getByTestId("report-row");
    await expect(rows).toHaveCount(3);
    await expect(rows.first()).toContainText("Revision 1");
    await expect(
      page.getByText(/cannot be deleted: the reports point at its revisions/),
    ).toBeVisible();
  });

  test("duplicates a revision into a new scenario", async ({ page }) => {
    await seed(page);
    await page.goto("/notebook?scenario=4e2f6a8c-1b3d-4f5e-9a7c-0d2e4f6a8b1c");
    await page
      .getByTestId("revision-1")
      .getByRole("button", { name: "Duplicate as new scenario" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Northwind R&D +40% (copy of r1)", level: 2 }),
    ).toBeVisible();
    await expect(page.getByTestId("revision-1")).toContainText("duplicated from another scenario");
    await expect(page.getByText("2 of 2 scenarios")).toBeVisible();
  });

  test("compares revisions and blocks different cutoffs (FC-09)", async ({ page }) => {
    await seed(page);
    await page.goto("/notebook?scenario=4e2f6a8c-1b3d-4f5e-9a7c-0d2e4f6a8b1c");
    await expect(page.getByRole("region", { name: /differences/ })).toContainText("R&D change");
    await expect(page.getByRole("region", { name: /differences/ })).toContainText(
      "+2 p.p. of revenue",
    );

    const other = JSON.parse(EXPORT_TEXT) as {
      scenarios: { scenario_id: string; name: string; revisions: { draft: { as_of: string } }[] }[];
      reports: unknown[];
    };
    const scenario = other.scenarios[0];
    if (!scenario) throw new Error("fixture");
    scenario.scenario_id = "7c1e3a5b-2d4f-4e6a-8b0c-9d1f3a5c7e2b";
    scenario.name = "Northwind at the September cutoff";
    for (const revision of scenario.revisions) revision.draft.as_of = "2022-09-30";
    other.reports = [];
    for (const item of scenario.revisions as { exported?: boolean }[]) item.exported = false;
    await importInput(page).setInputFiles({
      name: "september.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(other)),
    });
    await expect(page.getByText(/Imported september\.json: 1 added/)).toBeVisible();
    await page
      .getByRole("combobox", { name: "Second revision" })
      .selectOption({ label: "Northwind at the September cutoff · revision 1" });
    await expect(page.getByText("Comparison blocked")).toBeVisible();
    await expect(
      page.getByText("Different knowledge cutoffs (2022-12-31 and 2022-09-30)."),
    ).toBeVisible();
    await saveScreen(page, `notebook-compare-${test.info().project.name}`);
  });

  test("searches by tag and text", async ({ page }) => {
    await seed(page);
    await page.goto("/notebook");
    await page.getByRole("searchbox", { name: "Search" }).fill("nwsc");
    await expect(page.getByText("1 of 1 scenario")).toBeVisible();
    await page.getByRole("searchbox", { name: "Search" }).fill("capex");
    await expect(page.getByText("No scenario matches.")).toBeVisible();
    await page.getByRole("searchbox", { name: "Search" }).fill("");
    await page.getByRole("combobox", { name: "Tag" }).selectOption("rnd");
    await expect(page.getByText("1 of 1 scenario")).toBeVisible();
  });

  test("rejects broken or newer files and imports a notebook once", async ({ page }) => {
    await page.goto("/notebook");
    await importInput(page).setInputFiles({
      name: "broken.json",
      mimeType: "application/json",
      buffer: Buffer.from("{oops"),
    });
    await expect(page.getByText("The file is not valid JSON.")).toBeVisible();

    const newer = JSON.parse(EXPORT_TEXT) as Record<string, unknown>;
    newer["schema_version"] = 2;
    await importInput(page).setInputFiles({
      name: "newer.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(newer)),
    });
    await expect(page.getByText(/written by a newer version of MULTIVERSE/)).toBeVisible();
    await expect(page.getByText("No saved scenarios yet")).toBeVisible();

    await importInput(page).setInputFiles({
      name: "notebook.json",
      mimeType: "application/json",
      buffer: Buffer.from(EXPORT_TEXT),
    });
    await expect(page.getByText(/Imported notebook\.json: 1 added; 1 reports added/)).toBeVisible();
    await importInput(page).setInputFiles({
      name: "notebook.json",
      mimeType: "application/json",
      buffer: Buffer.from(EXPORT_TEXT),
    });
    await expect(page.getByText(/1 already here/)).toBeVisible();
  });

  test("has no WCAG 2.2 A or AA violations with a scenario open", async ({ page }) => {
    await seed(page);
    await page.goto("/notebook?scenario=4e2f6a8c-1b3d-4f5e-9a7c-0d2e4f6a8b1c");
    await expect(
      page.getByRole("heading", { name: "Revisions", exact: true, level: 3 }),
    ).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  });
});

test.describe("Storage failures (FC-10)", () => {
  test("keeps working in a private window and says nothing is saved", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "localStorage", {
        get() {
          throw new DOMException("The operation is insecure.", "SecurityError");
        },
      });
    });
    await page.goto("/notebook");
    await expect(page.getByText("This browser does not allow storage here")).toBeVisible();
    await saveScreen(page, `notebook-private-${test.info().project.name}`);
  });

  test("reports a full storage when saving", async ({ page }) => {
    await page.addInitScript(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key: string, value: string) {
        if (key === "multiverse.notebook")
          throw new DOMException("Quota exceeded", "QuotaExceededError");
        return original.call(this, key, value);
      };
    });
    await validRnd(page);
    await page.getByRole("button", { name: "Save to notebook" }).click();
    await page
      .getByRole("dialog", { name: "Save to notebook" })
      .getByRole("button", { name: "Save", exact: true })
      .click();
    await expect(
      page.getByText(/storage is full, so the scenario is kept only until you close the tab/),
    ).toBeVisible();
  });

  test("never overwrites unreadable data without a decision", async ({ page }) => {
    await seed(page, "{broken");
    await page.goto("/notebook");
    await expect(page.getByText("Saved data on this device cannot be read")).toBeVisible();
    await expect(page.getByRole("button", { name: "Download the unreadable data" })).toBeVisible();
    await page.getByRole("button", { name: "Start an empty notebook" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete and start empty" }).click();
    await expect(page.getByText("No saved scenarios yet")).toBeVisible();
  });
});

test.describe("Settings & Privacy", () => {
  test("lists what is stored and deletes everything after confirmation (FR-ST-02)", async ({
    page,
  }) => {
    await seed(page);
    await page.goto("/settings");
    await expect(page.getByTestId("storage-items")).toContainText("multiverse.notebook");
    await page.getByRole("button", { name: "Delete all data on this device" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete everything" }).click();
    await expect(page.getByText("All MULTIVERSE data on this device was deleted.")).toBeVisible();
    await expect(page.getByTestId("storage-empty")).toBeVisible();
    await page.goto("/notebook");
    await expect(page.getByText("No saved scenarios yet")).toBeVisible();
  });
});
