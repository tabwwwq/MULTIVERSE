import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";

const SCREENS_DIR = fileURLToPath(
  new URL(`../../../docs/stages/${process.env["SAVE_SCREENS"] ?? "screens"}/`, import.meta.url),
);

async function saveScreen(page: Page, name: string): Promise<void> {
  if (!process.env["SAVE_SCREENS"]) return;
  mkdirSync(SCREENS_DIR, { recursive: true });
  await page.screenshot({ path: `${SCREENS_DIR}${name}.png` });
}

test.describe("keyboard", () => {
  test("the skip link is the first stop and moves focus to the main content", async ({ page }) => {
    await page.goto("/methodology");
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeFocused();
  });

  test("the scenario launch button is disabled and explains why", async ({ page }) => {
    await page.goto("/");
    const launch = page.getByRole("button", { name: "Launch a scenario" });
    await expect(launch).toBeDisabled();
    await expect(launch).toHaveAccessibleDescription(/not built yet/);
  });
});

const SIDEBAR_BREAKPOINT = 1024;

test.describe("desktop sidebar", () => {
  test.skip(
    ({ viewport }) => (viewport?.width ?? 0) < SIDEBAR_BREAKPOINT,
    "The sidebar is shown from 1024px",
  );

  test("marks the current page and lists planned sections with their stage", async ({ page }) => {
    await page.goto("/methodology");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link", { name: "Methodology" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(
      nav.getByRole("link", { name: "Decision Builder planned, Stage 05" }),
    ).toBeVisible();
  });

  test("collapses, keeps labels for screen readers and remembers the choice", async ({ page }) => {
    await page.goto("/");
    const toggle = page.getByRole("button", { name: "Collapse navigation" });
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await toggle.click();
    const expand = page.getByRole("button", { name: "Expand navigation" });
    await expect(expand).toHaveAttribute("aria-expanded", "false");
    await expect(
      page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Methodology" }),
    ).toBeAttached();
    await page.reload();
    await expect(page.getByRole("button", { name: "Expand navigation" })).toBeVisible();
    await page.getByRole("button", { name: "Expand navigation" }).click();
  });
});

test.describe("navigation drawer", () => {
  test.skip(
    ({ viewport }) => (viewport?.width ?? 0) >= SIDEBAR_BREAKPOINT,
    "The drawer replaces the sidebar below 1024px",
  );

  test("opens from the menu button, closes with Escape and returns focus", async ({
    page,
  }, testInfo) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const trigger = page.getByRole("button", { name: "Open navigation" });
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    const drawerNav = page.locator("#nav-drawer").getByRole("navigation", { name: "Main" });
    await expect(drawerNav).toBeFocused();
    await expect(page.locator("#app-frame")).toHaveJSProperty("inert", true);
    await saveScreen(page, `drawer-${testInfo.project.name}`);

    await page.keyboard.press("Escape");
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(trigger).toBeFocused();
    await expect(page.locator("#app-frame")).toHaveJSProperty("inert", false);
  });

  test("navigates and closes when a link is chosen", async ({ page }) => {
    await page.goto("/");
    const trigger = page.getByRole("button", { name: "Open navigation" });
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    await page.locator("#nav-drawer").getByRole("link", { name: "Methodology" }).click();
    await expect(page).toHaveURL(/\/methodology$/);
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("heading", { level: 1, name: "Methodology" })).toBeVisible();
  });
});

test.describe("dialog", () => {
  test("puts focus on the safe action and returns it to the trigger on Escape", async ({
    page,
  }, testInfo) => {
    await page.goto("/design-system");
    const trigger = page.getByRole("button", { name: "Open example dialog" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Discard changes to this scenario?" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Keep editing" })).toBeFocused();
    await saveScreen(page, `dialog-${testInfo.project.name}`);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});

test.describe("motion", () => {
  test("the hero draws in once when motion is allowed", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.goto("/");
    const name = await page
      .getByTestId("timeline-motif")
      .locator(".motif-observed")
      .evaluate((element) => getComputedStyle(element).animationName);
    expect(name).toBe("motif-draw");
  });

  test("the hero is static with reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const style = await page
      .getByTestId("timeline-motif")
      .locator(".motif-observed")
      .evaluate((element) => {
        const computed = getComputedStyle(element);
        return { animation: computed.animationName, dash: computed.strokeDasharray };
      });
    expect(style).toEqual({ animation: "none", dash: "none" });
  });
});

test.describe("table", () => {
  test("turns into labelled cards on narrow screens and keeps columns on wide ones", async ({
    page,
  }, testInfo) => {
    await page.goto("/design-system");
    const region = page.getByRole("region", { name: /Northwind Semiconductors/ });
    await expect(region).toBeVisible();
    const headDisplay = await region
      .locator("thead")
      .evaluate((element) => getComputedStyle(element).display);
    if (testInfo.project.name === "mobile") {
      expect(headDisplay).toBe("none");
      const label = await region
        .locator("td")
        .first()
        .evaluate((element) => getComputedStyle(element, "::before").content);
      expect(label).toBe('"Revenue"');
    } else {
      expect(headDisplay).not.toBe("none");
    }
  });
});
