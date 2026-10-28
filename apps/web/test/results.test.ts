import { MOCK_RESULTS } from "@multiverse/contracts/mock-results";
import type { ScenarioResult } from "@multiverse/contracts";
import { describe, expect, it } from "vitest";
import { compatibility } from "@/results/compare";
import { formatQuantiles, formatTick, formatValue } from "@/results/format";
import { parseResultParams } from "@/results/params";
import { createMockResultRepository } from "@/results/repository";
import { axisFor } from "@/results/scale";
import {
  buildChartModel,
  chartSummary,
  csvFileName,
  kpisFromChart,
  metricOf,
  modeOptions,
  type SeriesKey,
  tableRows,
  toCsv,
} from "@/results/series";

function byTitle(fragment: string): ScenarioResult {
  const result = MOCK_RESULTS.find((candidate) => candidate.title.includes(fragment));
  if (!result) throw new Error(`no mock result ${fragment}`);
  return result;
}

const RND = byTitle("R&D");
const CAPEX = byTitle("CAPEX");
const WORKFORCE = byTitle("workforce");
const FAILED = byTitle("failed");
const ALL: ReadonlySet<SeriesKey> = new Set(["observed", "baseline", "alt_a", "alt_b"]);

describe("chart model", () => {
  it("shows history, the baseline and both alternates in absolute mode", () => {
    const model = buildChartModel(RND, "revenue", "absolute");
    expect(model.series.map((series) => series.key)).toEqual([
      "observed",
      "baseline",
      "alt_a",
      "alt_b",
    ]);
    expect(model.series[0]?.points.at(-1)?.label).toBe("FY2022 Q3");
    expect(model.series[1]?.points[0]?.label).toBe("FY2022 Q4");
    expect(model.series[1]?.points).toHaveLength(RND.horizon_quarters);
  });

  it("takes KPI values from the chart's own last points (FR-RE-07)", () => {
    for (const mode of ["absolute", "change"] as const) {
      const model = buildChartModel(RND, "ebitda", mode);
      for (const kpi of kpisFromChart(model)) {
        const series = model.series.find((candidate) => candidate.key === kpi.key);
        expect(kpi.point).toBe(series?.points.at(-1));
      }
    }
  });

  it("matches the result's numbers exactly", () => {
    const model = buildChartModel(RND, "revenue", "absolute");
    const forecast = metricOf(RND, "revenue").forecasts.find((f) => f.scenario === "alt_b");
    const last = forecast?.points.at(-1);
    expect(kpisFromChart(model).find((kpi) => kpi.key === "alt_b")?.point.raw).toEqual({
      p10: last?.p10,
      p50: last?.p50,
      p90: last?.p90,
    });
  });

  it("uses paired path-by-path changes, not the difference of the bands", () => {
    const model = buildChartModel(RND, "revenue", "change");
    const paired = metricOf(RND, "revenue").changes.find(
      (change) => change.scenario === "alt_a" && change.unit === "currency",
    );
    const alt = model.series.find((series) => series.key === "alt_a");
    expect(alt?.points.map((point) => point.raw.p10)).toEqual(
      paired?.points.map((point) => point.p10),
    );
    expect(
      model.series.find((series) => series.key === "baseline")?.points.every((p) => p.p50 === 0),
    ).toBe(true);
    expect(model.series.some((series) => series.key === "observed")).toBe(false);
  });

  it("offers percent only where the baseline stays positive (FP-08)", () => {
    expect(modeOptions(RND, "revenue").find((option) => option.mode === "percent")?.available).toBe(
      true,
    );
    const netDebt = modeOptions(RND, "net_debt").find((option) => option.mode === "percent");
    expect(netDebt?.available).toBe(false);
    expect(netDebt?.reason).toContain("Undefined");
  });

  it("builds table rows from the same points", () => {
    const model = buildChartModel(RND, "fcf", "absolute");
    const rows = tableRows(model, ALL);
    const points = model.series.reduce((sum, series) => sum + series.points.length, 0);
    expect(rows.reduce((sum, row) => sum + Object.keys(row.cells).length, 0)).toBe(points);
  });
});

describe("honest axes (FP-09)", () => {
  it("include zero for absolute values", () => {
    const model = buildChartModel(RND, "revenue", "absolute");
    expect(model.axis.min).toBeLessThanOrEqual(0);
    expect(model.axis.max).toBeGreaterThanOrEqual(
      Math.max(...model.series.flatMap((s) => s.points.map((p) => p.p90))),
    );
  });

  it("centre changes on zero", () => {
    const model = buildChartModel(RND, "ebitda", "change");
    expect(model.axis.min).toBe(-model.axis.max);
  });

  it("produce round ticks", () => {
    expect(axisFor([120, 870], "include_zero", 4).ticks).toEqual([0, 250, 500, 750, 1000]);
  });
});

describe("number formatting (FP-02)", () => {
  it("rounds a median to what its interval allows", () => {
    const point = { p10: 1_295_359_735, p50: 1_672_323_449, p90: 2_139_595_978 };
    expect(formatQuantiles(point, "usd")).toEqual({
      median: "USD 1.7bn",
      range: "USD 1.3bn to USD 2.1bn",
    });
  });

  it("keeps more digits for a narrow interval and signs changes", () => {
    expect(formatValue(-47_220_000, "usd", { signed: true, width: 200_000 })).toBe("−USD 47.2m");
    expect(formatValue(-47_220_000, "usd", { signed: true, width: 2_000_000 })).toBe("−USD 47m");
    expect(formatValue(0.0123, "fraction", { signed: true, width: 0.002 })).toBe("+1.2%");
    expect(formatTick(1_500_000_000, "usd", false)).toBe("1.5bn");
  });
});

describe("CSV export (SYN-05)", () => {
  const model = buildChartModel(RND, "revenue", "absolute");
  const csv = toCsv(model, RND, ALL);
  const lines = csv.trim().split("\n");

  it("starts with a synthetic-data warning and marks the file name", () => {
    expect(lines[0]).toMatch(/^# SYNTHETIC DEMO DATA/);
    expect(csvFileName(model, RND)).toMatch(/_DEMO\.csv$/);
  });

  it("contains exactly the plotted points with exact values", () => {
    const points = model.series.reduce((sum, series) => sum + series.points.length, 0);
    expect(lines).toHaveLength(points + 2);
    const last = model.series.at(-1)?.points.at(-1);
    expect(csv).toContain(`${last?.raw.p10},${last?.raw.p50},${last?.raw.p90},USD`);
  });

  it("leaves hidden series out", () => {
    const visible = new Set<SeriesKey>(["observed", "baseline"]);
    expect(toCsv(model, RND, visible)).not.toContain("R&D +40%");
  });
});

describe("summary for screen readers", () => {
  it("names the horizon medians, the quantile type and the mock origin", () => {
    const text = chartSummary(buildChartModel(RND, "revenue", "absolute"), ALL);
    expect(text).toContain("At FY2025 Q3");
    expect(text).toContain("Baseline: median USD 1.7bn");
    expect(text).toContain("Mock data, conditional model quantiles, not calibrated.");
  });
});

describe("compare compatibility (FR-RE-06, FC-09)", () => {
  it("allows results on the same footing and notices shared baselines", () => {
    expect(compatibility(RND, CAPEX)).toEqual({
      compatible: true,
      reasons: [],
      pairedBaselines: true,
    });
  });

  it("blocks a different cutoff and failed runs", () => {
    const cutoff = compatibility(RND, WORKFORCE);
    expect(cutoff.compatible).toBe(false);
    expect(cutoff.reasons).toEqual([
      "The results have different knowledge cutoffs (2022-12-31 and 2022-06-30).",
    ]);
    expect(compatibility(RND, FAILED).reasons).toContain("Only completed results can be compared.");
  });
});

describe("result repository and links", () => {
  it("lists every mock result and finds one by ID", async () => {
    const repository = createMockResultRepository();
    expect(await repository.list()).toHaveLength(MOCK_RESULTS.length);
    expect((await repository.get(RND.result_id))?.title).toBe(RND.title);
    expect(await repository.get("00000000-0000-4000-8000-000000000000")).toBeNull();
  });

  it("ignores unknown link values by name", () => {
    const parsed = parseResultParams({ metric: "<script>", mode: "percent", with: "nope" }, [
      RND.result_id,
    ]);
    expect(parsed).toEqual({
      metric: "revenue",
      mode: "percent",
      compareWith: null,
      ignored: ["metric", "with"],
    });
  });
});
