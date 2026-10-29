import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { type Browser, type Page, test } from "@playwright/test";

/*
 * Performance observations for Gate A (TC-20, NFR-PERF-01 and NFR-PERF-02). They are
 * measurements, not assertions, so they only run on request:
 *   OBSERVE_PERF=1 npx playwright test performance --project=desktop
 * Cold loads of the production build on this machine, with the network shaped like
 * Lighthouse's desktop profile (40 ms round trip, 10 Mbit/s). The numbers go to
 * test-results/performance.json and to the console.
 */

test.skip(!process.env["OBSERVE_PERF"], "Set OBSERVE_PERF=1 to measure");

const NORTHWIND = "5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13";
const RND_RESULT = "2d7c9e41-5b3a-4f6e-8c1d-9a0b7e6f5c34";
const RUNS = 10;
const PAGES = [
  "/",
  "/universe",
  `/dossier/${NORTHWIND}`,
  `/decisions?company=${NORTHWIND}`,
  `/timeline/${RND_RESULT}`,
  `/compare/${RND_RESULT}`,
  "/notebook",
];

interface Load {
  ttfb: number;
  dcl: number;
  load: number;
  lcp: number;
  cls: number;
  jsTransfer: number;
  jsDecoded: number;
  transfer: number;
}

const nearestRank = (values: number[], share: number): number => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(share * sorted.length) - 1)] ?? Number.NaN;
};

async function shapedPage(browser: Browser, cpuSlowdown = 1): Promise<Page> {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 40,
    downloadThroughput: (10 * 1024 * 1024) / 8,
    uploadThroughput: (10 * 1024 * 1024) / 8,
  });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: cpuSlowdown });
  return page;
}

async function measureLoad(page: Page, route: string): Promise<Load> {
  await page.goto(route, { waitUntil: "load" });
  await page.waitForTimeout(500);
  return page.evaluate(async () => {
    const lcp = await new Promise<number>((resolve) => {
      new PerformanceObserver((list) => {
        const entries = list.getEntries();
        resolve(entries[entries.length - 1]?.startTime ?? Number.NaN);
      }).observe({ type: "largest-contentful-paint", buffered: true });
      setTimeout(() => resolve(Number.NaN), 2000);
    });
    let cls = 0;
    for (const entry of performance.getEntriesByType("layout-shift") as unknown as {
      value: number;
      hadRecentInput: boolean;
    }[]) {
      if (!entry.hadRecentInput) cls += entry.value;
    }
    const [nav] = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
    const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
    const scripts = resources.filter((entry) => entry.name.split("?")[0]?.endsWith(".js"));
    const sum = (list: PerformanceResourceTiming[], key: "transferSize" | "decodedBodySize") =>
      list.reduce((total, entry) => total + entry[key], 0);
    return {
      ttfb: nav?.responseStart ?? Number.NaN,
      dcl: nav?.domContentLoadedEventEnd ?? Number.NaN,
      load: nav?.loadEventEnd ?? Number.NaN,
      lcp,
      cls,
      jsTransfer: sum(scripts, "transferSize"),
      jsDecoded: sum(scripts, "decodedBodySize"),
      transfer: sum(resources, "transferSize") + (nav?.transferSize ?? 0),
    };
  });
}

/** Longest interaction (Event Timing) while the steps run: the page's INP estimate. */
async function longestInteraction(
  page: Page,
  steps: (page: Page) => Promise<void>,
): Promise<number> {
  await page.evaluate(() => {
    const store = window as unknown as { __longest: number };
    store.__longest = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as unknown as {
        interactionId: number;
        duration: number;
      }[]) {
        if (entry.interactionId > 0) store.__longest = Math.max(store.__longest, entry.duration);
      }
    }).observe({ type: "event", buffered: true, durationThreshold: 16 } as PerformanceObserverInit);
  });
  await steps(page);
  await page.waitForTimeout(500);
  return page.evaluate(() => (window as unknown as { __longest: number }).__longest);
}

const INTERACTIONS: { name: string; route: string; steps: (page: Page) => Promise<void> }[] = [
  {
    name: "Universe search, typing",
    route: "/universe",
    steps: async (page) => {
      await page.getByRole("searchbox", { name: "Search" }).click();
      await page.keyboard.type("north", { delay: 80 });
      await page.waitForURL(/q=north/);
    },
  },
  {
    name: "Decision Builder, validate",
    route: `/decisions?company=${NORTHWIND}&type=rnd_change`,
    steps: async (page) => {
      await page.getByRole("textbox", { name: /^R&D change/ }).fill("25");
      await page.getByRole("button", { name: "Validate", exact: true }).click();
      await page.getByTestId("validation-status").waitFor();
    },
  },
  {
    name: "Timeline, metric, mode and table",
    route: `/timeline/${RND_RESULT}`,
    steps: async (page) => {
      await page.getByText("EBITDA (calculated)", { exact: true }).click();
      await page.getByText("Change vs baseline").click();
      await page.getByRole("button", { name: "Show as table" }).click();
    },
  },
];

test("observes load and interaction timings (TC-20)", async ({ browser }) => {
  test.skip(test.info().project.name !== "desktop", "Measured once, at desktop size");
  test.setTimeout(600_000);
  const report: Record<string, unknown> = {
    measured: new Date().toISOString(),
    runs: RUNS,
    network: "40 ms RTT, 10 Mbit/s",
  };

  const loads: Record<string, Record<string, number>> = {};
  for (const route of PAGES) {
    const samples: Load[] = [];
    for (let run = 0; run < RUNS; run += 1) {
      const page = await shapedPage(browser);
      samples.push(await measureLoad(page, route));
      await page.context().close();
    }
    const of = (key: keyof Load) => samples.map((sample) => sample[key]);
    loads[route] = {
      ttfbMedian: nearestRank(of("ttfb"), 0.5),
      loadMedian: nearestRank(of("load"), 0.5),
      loadP95: nearestRank(of("load"), 0.95),
      lcpMedian: nearestRank(of("lcp"), 0.5),
      lcpP95: nearestRank(of("lcp"), 0.95),
      clsMax: Math.max(...of("cls")),
      jsTransferKB: (samples[0]?.jsTransfer ?? 0) / 1024,
      jsDecodedKB: (samples[0]?.jsDecoded ?? 0) / 1024,
      transferKB: (samples[0]?.transfer ?? 0) / 1024,
    };
  }
  report["loads"] = loads;

  const interactions: Record<string, Record<string, number>> = {};
  for (const slowdown of [1, 4]) {
    for (const { name, route, steps } of INTERACTIONS) {
      const durations: number[] = [];
      for (let run = 0; run < 5; run += 1) {
        const page = await shapedPage(browser, slowdown);
        await page.goto(route, { waitUntil: "networkidle" });
        durations.push(await longestInteraction(page, steps));
        await page.context().close();
      }
      interactions[`${name} (CPU x${slowdown})`] = {
        median: nearestRank(durations, 0.5),
        max: Math.max(...durations),
      };
    }
  }
  report["interactions"] = interactions;

  const out = fileURLToPath(new URL("../test-results/", import.meta.url));
  mkdirSync(out, { recursive: true });
  writeFileSync(`${out}performance.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
});
