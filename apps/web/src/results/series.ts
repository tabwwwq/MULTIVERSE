import type {
  MetricResult,
  QuantilePoint,
  ResultMetric,
  ScenarioResult,
} from "@multiverse/contracts";
import { formatQuantiles, formatValue, type ValueUnit } from "@/results/format";
import { axisFor, type Axis } from "@/results/scale";

/*
 * The one data model behind every view of a result (PRD FR-RE-07): the chart, the KPI
 * cards, the table, the CSV and the screen-reader summary all read these series, so a
 * number cannot differ between them. Values stay exact decimal strings; numbers are
 * derived for plotting only.
 */

export type ChartMode = "absolute" | "change" | "percent";
export type SeriesKey = "observed" | "baseline" | "alt_a" | "alt_b";

export const MODE_LABELS: Record<ChartMode, string> = {
  absolute: "Absolute",
  change: "Change vs baseline",
  percent: "Percent vs baseline",
};

export interface ChartPoint {
  end: string;
  label: string;
  /** Exact values from the result; equal for an observed point. */
  raw: { p10: string; p50: string; p90: string };
  p10: number;
  p50: number;
  p90: number;
  source: { id: string; filedAt: string } | null;
}

export interface ChartSeries {
  key: SeriesKey;
  label: string;
  kind: "observed" | "forecast";
  points: ChartPoint[];
}

export interface ChartModel {
  resultId: string;
  metric: ResultMetric;
  metricLabel: string;
  definition: string;
  mode: ChartMode;
  unit: ValueUnit;
  series: ChartSeries[];
  /** Knowledge cutoff, and the last quarter that was public by then. */
  cutoff: string;
  lastObserved: string | null;
  axis: Axis;
  note: string | null;
}

export interface ModeOption {
  mode: ChartMode;
  available: boolean;
  reason: string | null;
}

function toPoint(point: QuantilePoint): ChartPoint {
  return {
    end: point.period_end,
    label: point.fiscal_label,
    raw: { p10: point.p10, p50: point.p50, p90: point.p90 },
    p10: Number(point.p10),
    p50: Number(point.p50),
    p90: Number(point.p90),
    source: null,
  };
}

export function metricOf(result: ScenarioResult, metric: ResultMetric): MetricResult {
  const found = result.metrics.find((candidate) => candidate.metric === metric);
  if (!found) throw new Error(`Result ${result.result_id} has no ${metric}`);
  return found;
}

export function scenarioLabel(result: ScenarioResult, key: SeriesKey): string {
  if (key === "observed") return "Observed";
  return result.scenarios.find((run) => run.key === key)?.label ?? key;
}

/** Percent needs a baseline that stays positive; the result omits it otherwise (FP-08). */
export function modeOptions(result: ScenarioResult, metric: ResultMetric): ModeOption[] {
  const data = metricOf(result, metric);
  const hasPercent = data.changes.some((change) => change.unit === "fraction_of_baseline");
  return (["absolute", "change", "percent"] as const).map((mode) => ({
    mode,
    available: mode !== "percent" || hasPercent,
    reason:
      mode === "percent" && !hasPercent
        ? `Undefined for ${data.label.toLowerCase()}: the baseline can be zero or negative.`
        : null,
  }));
}

export function buildChartModel(
  result: ScenarioResult,
  metric: ResultMetric,
  mode: ChartMode,
): ChartModel {
  const data = metricOf(result, metric);
  const alternates = result.scenarios.filter((run) => run.key !== "baseline");
  const series: ChartSeries[] = [];
  let note: string | null = null;
  const unit: ValueUnit = mode === "percent" ? "fraction" : "usd";

  if (mode === "absolute") {
    series.push({
      key: "observed",
      label: "Observed",
      kind: "observed",
      points: data.observed.map((point) => ({
        end: point.period_end,
        label: point.fiscal_label,
        raw: { p10: point.value, p50: point.value, p90: point.value },
        p10: Number(point.value),
        p50: Number(point.value),
        p90: Number(point.value),
        source: { id: point.source_id, filedAt: point.filed_at },
      })),
    });
    for (const forecast of data.forecasts) {
      series.push({
        key: forecast.scenario,
        label: scenarioLabel(result, forecast.scenario),
        kind: "forecast",
        points: forecast.points.map(toPoint),
      });
    }
  } else {
    const changeUnit = mode === "percent" ? "fraction_of_baseline" : "currency";
    const baseline = data.forecasts.find((forecast) => forecast.scenario === "baseline");
    // The baseline is zero against itself by definition; history has no counterfactual.
    series.push({
      key: "baseline",
      label: "Baseline",
      kind: "forecast",
      points: (baseline?.points ?? []).map((point) =>
        toPoint({ ...point, p10: "0", p50: "0", p90: "0" }),
      ),
    });
    for (const run of alternates) {
      const change = data.changes.find(
        (candidate) => candidate.scenario === run.key && candidate.unit === changeUnit,
      );
      if (change) {
        series.push({
          key: run.key,
          label: run.label,
          kind: "forecast",
          points: change.points.map(toPoint),
        });
      }
    }
    note =
      "Differences are computed path by path against the paired baseline, then summarized as quantiles. History has no alternative, so it is not shown.";
  }

  const values = series.flatMap((item) => item.points.flatMap((point) => [point.p10, point.p90]));
  return {
    resultId: result.result_id,
    metric,
    metricLabel: data.label,
    definition: data.definition,
    mode,
    unit,
    series,
    cutoff: result.as_of,
    lastObserved: data.observed.at(-1)?.period_end ?? null,
    axis: axisFor(values, mode === "absolute" ? "include_zero" : "symmetric_zero"),
    note,
  };
}

export interface Kpi {
  key: SeriesKey;
  label: string;
  point: ChartPoint;
}

/** KPI cards read the last point of each forecast series: the chart's own numbers. */
export function kpisFromChart(model: ChartModel): Kpi[] {
  return model.series
    .filter((series) => series.kind === "forecast" && series.points.length > 0)
    .filter((series) => model.mode === "absolute" || series.key !== "baseline")
    .map((series) => ({
      key: series.key,
      label: series.label,
      point: series.points.at(-1) as ChartPoint,
    }));
}

export interface TableRow {
  end: string;
  label: string;
  cells: Partial<Record<SeriesKey, ChartPoint>>;
}

export function tableRows(model: ChartModel, visible: ReadonlySet<SeriesKey>): TableRow[] {
  const rows = new Map<string, TableRow>();
  for (const series of model.series) {
    if (!visible.has(series.key)) continue;
    for (const point of series.points) {
      const row = rows.get(point.end) ?? { end: point.end, label: point.label, cells: {} };
      row.cells[series.key] = point;
      rows.set(point.end, row);
    }
  }
  return [...rows.values()].sort((a, b) => a.end.localeCompare(b.end));
}

export function quarterCount(model: ChartModel): number {
  return new Set(model.series.flatMap((series) => series.points.map((point) => point.end))).size;
}

function csvCell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

/** CSV of exactly the plotted points; the first line says the data are synthetic (SYN-05). */
export function toCsv(
  model: ChartModel,
  result: ScenarioResult,
  visible: ReadonlySet<SeriesKey>,
): string {
  const warning =
    `# SYNTHETIC DEMO DATA - mock result, not a forecast. ${result.title}. ` +
    `Metric: ${model.metricLabel}. Mode: ${MODE_LABELS[model.mode]}. ` +
    `Quantiles: conditional model quantiles, not calibrated. Cutoff ${result.as_of}. Result ${result.result_id}.`;
  const unit = model.unit === "fraction" ? "fraction_of_baseline" : result.currency;
  const lines = [warning, "period_end,fiscal_label,series,kind,p10,p50,p90,unit,source"];
  for (const series of model.series) {
    if (!visible.has(series.key)) continue;
    for (const point of series.points) {
      lines.push(
        [
          point.end,
          point.label,
          series.label,
          series.kind,
          point.raw.p10,
          point.raw.p50,
          point.raw.p90,
          unit,
          point.source ? `${point.source.id} filed ${point.source.filedAt}` : "mock quantiles",
        ]
          .map(csvCell)
          .join(","),
      );
    }
  }
  return `${lines.join("\n")}\n`;
}

export function csvFileName(model: ChartModel, result: ScenarioResult): string {
  const slug = result.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `multiverse_${slug}_${model.metric}_${model.mode}_DEMO.csv`;
}

/** Plain-language summary for screen readers and as the visible chart caption. */
export function chartSummary(model: ChartModel, visible: ReadonlySet<SeriesKey>): string {
  const kpis = kpisFromChart(model).filter((kpi) => visible.has(kpi.key));
  const signed = model.mode !== "absolute";
  const horizon = kpis[0]?.point.label;
  const parts = kpis.map((kpi) => {
    const { median, range } = formatQuantiles(kpi.point, model.unit, signed);
    return `${kpi.label}: median ${median}, p10 to p90 ${range}`;
  });
  const history =
    model.mode === "absolute" && model.lastObserved
      ? `History up to ${model.series[0]?.points.at(-1)?.label ?? model.lastObserved}, public by the cutoff ${model.cutoff}. `
      : "";
  const what =
    model.mode === "absolute"
      ? model.metricLabel
      : `${model.metricLabel}, ${MODE_LABELS[model.mode].toLowerCase()}`;
  return `${what}. ${history}${horizon ? `At ${horizon}: ${parts.join("; ")}.` : ""} Mock data, conditional model quantiles, not calibrated.`;
}

/** Absolute value with its unit for tooltips and tables. */
export function pointText(point: ChartPoint, unit: ValueUnit, signed: boolean): string {
  if (point.p10 === point.p90) return formatValue(point.p50, unit, { signed });
  const { median, range } = formatQuantiles(point, unit, signed);
  return `${median} (${range})`;
}
