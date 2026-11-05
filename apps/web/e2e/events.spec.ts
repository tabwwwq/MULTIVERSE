import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

interface Row {
  event_id: string;
  company: string;
  event_type: string;
  confounded_by?: string[];
}

const path = fileURLToPath(new URL("../../../data/events/registry.json", import.meta.url));
const EVENTS = (JSON.parse(readFileSync(path, "utf8")) as { events: Row[] }).events;
const first = EVENTS.find((event) => (event.confounded_by ?? []).length > 0);

test.describe("Event Registry", () => {
  test("says that causal work is blocked and keeps its rejections", async ({ page }) => {
    await page.goto("/events");
    await expect(page.getByRole("heading", { level: 1, name: "Event Registry" })).toBeVisible();
    await expect(page.getByText("Causal work is blocked")).toBeVisible();
    await expect(page.getByText("Single review by AI")).toBeVisible();
    await expect(page.getByText(/index lists Item 2.01/)).toBeVisible();
  });

  test("filters by type", async ({ page }) => {
    await page.goto("/events");
    await page.getByRole("link", { name: /^Layoff/ }).click();
    await expect(page).toHaveURL(/type=layoff/);
    // The table stacks into cards on a phone, so its links count the rows at every size.
    const rows = page.getByRole("region", { name: "Events of the registry" }).getByRole("link");
    const count = EVENTS.filter((event) => event.event_type === "layoff").length;
    await expect(rows).toHaveCount(count);
  });

  test("shows intention, execution, unknowns and the filing of an event", async ({ page }) => {
    if (!first) throw new Error("no confounded event");
    await page.goto(`/events/${first.event_id}`);
    await expect(page.getByRole("heading", { level: 1, name: first.company })).toBeVisible();
    await expect(page.getByText("Announced intention")).toBeVisible();
    await expect(page.getByText("This event does not stand alone")).toBeVisible();
    await expect(page.getByRole("link", { name: "Read the filing on sec.gov" })).toHaveAttribute(
      "href",
      /^https:\/\/www\.sec\.gov\/Archives\//,
    );
  });

  test("keeps a second review in this browser until it is downloaded", async ({ page }) => {
    if (!first) throw new Error("no confounded event");
    await page.goto(`/events/${first.event_id}`);
    await expect(page.getByRole("button", { name: "Download 0 reviews" })).toBeDisabled();
    await page.getByLabel("Decision").selectOption("corrected");
    await page.getByLabel("Notes").fill("The date differs in the exhibit.");
    await page.getByRole("button", { name: "Save review" }).click();
    await expect(page.getByText("Saved in this browser")).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download 1 reviews" }).click();
    expect((await download).suggestedFilename()).toBe("event-reviews.json");
    await page.reload();
    await expect(page.getByRole("button", { name: "Download 1 reviews" })).toBeEnabled();
  });

  test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
    if (!first) throw new Error("no confounded event");
    for (const route of ["/events", `/events/${first.event_id}`]) {
      await page.goto(route);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    }
  });
});
