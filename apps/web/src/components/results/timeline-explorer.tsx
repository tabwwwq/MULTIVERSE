"use client";

import type { ResultMetric, ScenarioResult } from "@multiverse/contracts";
import { Download, Table2 } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { LineKey } from "@/components/results/series-style";
import { TimelineChart } from "@/components/results/timeline-chart";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import {
  buildChartModel,
  type ChartMode,
  chartSummary,
  csvFileName,
  kpisFromChart,
  MODE_LABELS,
  modeOptions,
  pointText,
  type SeriesKey,
  type TableRow,
  tableRows,
  toCsv,
} from "@/results/series";
import { formatQuantiles } from "@/results/format";
import { cn } from "@/lib/cn";

const SEGMENT =
  "flex min-h-12 cursor-pointer items-center rounded-control border border-line-strong px-4 text-small text-ink " +
  "has-checked:border-mint has-checked:bg-inset has-disabled:cursor-not-allowed has-disabled:border-line " +
  "has-disabled:text-ink-muted has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-mint";

interface TimelineExplorerProps {
  result: ScenarioResult;
  initialMetric: ResultMetric;
  initialMode: ChartMode;
}

export function TimelineExplorer({ result, initialMetric, initialMode }: TimelineExplorerProps) {
  const [metric, setMetric] = useState<ResultMetric>(initialMetric);
  const [mode, setMode] = useState<ChartMode>(initialMode);
  const [hidden, setHidden] = useState<ReadonlySet<SeriesKey>>(new Set());
  const [showBands, setShowBands] = useState(true);
  const [showTable, setShowTable] = useState(false);
  const titleId = useId();
  const summaryId = useId();

  const options = modeOptions(result, metric);
  const effectiveMode = options.find((option) => option.mode === mode)?.available
    ? mode
    : "absolute";
  const model = useMemo(
    () => buildChartModel(result, metric, effectiveMode),
    [result, metric, effectiveMode],
  );
  const visible = useMemo(
    () => new Set(model.series.map((series) => series.key).filter((key) => !hidden.has(key))),
    [hidden, model],
  );
  const kpis = kpisFromChart(model).filter((kpi) => visible.has(kpi.key));
  const signed = model.mode !== "absolute";

  const sync = (nextMetric: ResultMetric, nextMode: ChartMode) => {
    const params = new URLSearchParams({ metric: nextMetric, mode: nextMode });
    window.history.replaceState(null, "", `?${params.toString()}`);
  };

  const download = () => {
    const blob = new Blob([toCsv(model, result, visible)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = csvFileName(model, result);
    link.click();
    URL.revokeObjectURL(url);
  };

  const columns = [
    { key: "label" as const, header: "Quarter", rowHeader: true },
    ...model.series
      .filter((series) => visible.has(series.key))
      .map((series) => ({
        key: "label" as const,
        id: series.key,
        header: series.kind === "observed" ? "Observed" : `${series.label} median (p10 to p90)`,
        numeric: true,
        render: (row: TableRow) => {
          const point = row.cells[series.key];
          return point ? pointText(point, model.unit, signed) : "—";
        },
      })),
  ];

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-5">
      <div className="flex flex-col gap-4">
        <fieldset className="flex min-w-0 flex-col gap-2">
          <legend className="text-small font-medium text-ink">Metric</legend>
          <div className="flex flex-wrap gap-2">
            {result.metrics.map((item) => (
              <label key={item.metric} className={SEGMENT}>
                <input
                  type="radio"
                  name="metric"
                  value={item.metric}
                  checked={metric === item.metric}
                  onChange={() => {
                    setMetric(item.metric);
                    sync(item.metric, mode);
                  }}
                  className="sr-only"
                />
                {item.label}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="flex min-w-0 flex-col gap-2">
          <legend className="text-small font-medium text-ink">Show</legend>
          <div className="flex flex-wrap gap-2">
            {options.map((option) => (
              <label key={option.mode} className={SEGMENT} title={option.reason ?? undefined}>
                <input
                  type="radio"
                  name="mode"
                  value={option.mode}
                  checked={effectiveMode === option.mode}
                  disabled={!option.available}
                  aria-describedby={option.reason ? `reason-${option.mode}` : undefined}
                  onChange={() => {
                    setMode(option.mode);
                    sync(metric, option.mode);
                  }}
                  className="sr-only"
                />
                {MODE_LABELS[option.mode]}
              </label>
            ))}
          </div>
          {options
            .filter((option) => option.reason)
            .map((option) => (
              <p
                key={option.mode}
                id={`reason-${option.mode}`}
                className="text-small text-ink-muted"
              >
                {MODE_LABELS[option.mode]}: {option.reason}
              </p>
            ))}
        </fieldset>
      </div>

      <div className="flex flex-col gap-3 rounded-panel border border-line bg-surface p-4 md:p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id={titleId} className="font-display text-h4 text-ink">
            {model.metricLabel}
            <span className="text-small font-normal text-ink-muted">
              {" "}
              · {MODE_LABELS[model.mode].toLowerCase()} ·{" "}
              {model.unit === "fraction" ? "% of baseline" : result.currency}
            </span>
          </h2>
        </div>
        <p id={summaryId} className="text-small text-ink-muted">
          {chartSummary(model, visible)}
        </p>
        <ul className="flex flex-wrap gap-2" aria-label="Series">
          {model.series.map((series) => {
            const on = visible.has(series.key);
            return (
              <li key={series.key}>
                <button
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setHidden((current) => {
                      const next = new Set(current);
                      if (on) next.add(series.key);
                      else next.delete(series.key);
                      return next;
                    })
                  }
                  className={cn(
                    "flex min-h-10 items-center gap-2 rounded-pill border px-3 text-small",
                    on ? "border-line-strong text-ink" : "border-line text-ink-muted line-through",
                  )}
                >
                  <LineKey series={series.key} />
                  {series.label}
                  {series.kind === "forecast" ? " (mock)" : ""}
                </button>
              </li>
            );
          })}
          <li>
            <button
              type="button"
              aria-pressed={showBands}
              onClick={() => setShowBands((current) => !current)}
              className={cn(
                "flex min-h-10 items-center gap-2 rounded-pill border px-3 text-small",
                showBands
                  ? "border-line-strong text-ink"
                  : "border-line text-ink-muted line-through",
              )}
            >
              <span aria-hidden="true" className="h-2.5 w-6 rounded-pill bg-observed/25" />
              p10 to p90 band
            </button>
          </li>
        </ul>
        <TimelineChart
          model={model}
          visible={visible}
          showBands={showBands}
          events={result.events}
          labelledBy={titleId}
          describedBy={summaryId}
        />
        <p className="text-micro text-ink-muted">
          Bands: conditional model quantiles p10 to p90 of {result.paths} mock paths, not
          calibrated: they are not a confidence interval and are not expected to contain the outcome
          80% of the time.
          {model.note ? ` ${model.note}` : ""}
        </p>
        <div className="flex flex-wrap gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowTable((current) => !current)}
            aria-expanded={showTable}
          >
            <Table2 aria-hidden="true" />
            {showTable ? "Hide table" : "Show as table"}
          </Button>
          <Button variant="secondary" size="sm" onClick={download}>
            <Download aria-hidden="true" />
            Download CSV
          </Button>
        </div>
        {showTable ? (
          <DataTable
            id={`table-${model.metric}-${model.mode}`}
            caption={`${model.metricLabel}, ${MODE_LABELS[model.mode].toLowerCase()}: every plotted point`}
            columns={columns}
            rows={tableRows(model, visible)}
            rowKey={(row) => row.end}
          />
        ) : null}
      </div>

      <section
        aria-label="Key figures at the horizon"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
      >
        {kpis.map((kpi) => {
          const { median, range } = formatQuantiles(kpi.point, model.unit, signed);
          return (
            <article
              key={kpi.key}
              className="flex flex-col gap-1 rounded-panel border border-line bg-surface p-4"
              data-testid={`kpi-${kpi.key}`}
            >
              <p className="flex items-center gap-2 text-small text-ink-muted">
                <LineKey series={kpi.key} width={16} />
                {kpi.label} · {kpi.point.label}
              </p>
              <p className="font-display text-h3 text-ink" data-testid={`kpi-${kpi.key}-median`}>
                {median}
              </p>
              <p className="text-small text-ink-muted">p10 to p90: {range}</p>
            </article>
          );
        })}
      </section>
    </section>
  );
}
