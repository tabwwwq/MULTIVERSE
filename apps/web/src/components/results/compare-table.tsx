import type { ResultMetric, ScenarioResult } from "@multiverse/contracts";
import { LineKey } from "@/components/results/series-style";
import { formatQuantiles } from "@/results/format";
import { buildChartModel, kpisFromChart, modeOptions } from "@/results/series";

/*
 * Side-by-side KPIs at the horizon (docs/02 Universe Compare). Every cell comes from
 * the same chart model as the Timeline Explorer, so the numbers match the charts.
 */

const METRICS: readonly ResultMetric[] = ["revenue", "ebitda", "fcf", "net_debt", "ev"];

export function CompareTable({ result, caption }: { result: ScenarioResult; caption: string }) {
  const runs = result.scenarios;
  const rows = METRICS.filter((metric) =>
    result.metrics.some((item) => item.metric === metric),
  ).map((metric) => {
    const absolute = kpisFromChart(buildChartModel(result, metric, "absolute"));
    const change = kpisFromChart(buildChartModel(result, metric, "change"));
    const percentAvailable = modeOptions(result, metric).find(
      (option) => option.mode === "percent",
    )?.available;
    const percent = percentAvailable
      ? kpisFromChart(buildChartModel(result, metric, "percent"))
      : [];
    return {
      metric,
      label: absolute[0]?.point ? buildChartModel(result, metric, "absolute").metricLabel : metric,
      absolute,
      change,
      percent,
    };
  });
  const horizon = rows[0]?.absolute[0]?.point.label ?? "";

  return (
    <div
      role="region"
      aria-labelledby={`${result.result_id}-caption`}
      tabIndex={0}
      className="data-table rounded-panel border border-line bg-surface"
    >
      <table>
        <caption id={`${result.result_id}-caption`}>
          {caption} · medians with p10 to p90 at {horizon}
        </caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {runs.map((run) => (
              <th key={run.key} scope="col">
                <span className="inline-flex items-center gap-2">
                  <LineKey series={run.key} width={16} />
                  {run.label}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.metric}>
              <th scope="row">{row.label}</th>
              {runs.map((run) => {
                const value = row.absolute.find((kpi) => kpi.key === run.key);
                const change = row.change.find((kpi) => kpi.key === run.key);
                const percent = row.percent.find((kpi) => kpi.key === run.key);
                const shown = value ? formatQuantiles(value.point, "usd") : null;
                const delta = change ? formatQuantiles(change.point, "usd", true) : null;
                const share = percent ? formatQuantiles(percent.point, "fraction", true) : null;
                return (
                  <td key={run.key} data-label={run.label} className="is-numeric">
                    {shown ? (
                      <span className="flex flex-col items-end gap-0.5">
                        <span className="text-ink">{shown.median}</span>
                        <span className="text-micro text-ink-muted">{shown.range}</span>
                        {delta ? (
                          <span className="text-micro text-ink">
                            vs baseline {delta.median}
                            {share ? ` (${share.median})` : ""}
                          </span>
                        ) : null}
                        {delta ? (
                          <span className="text-micro text-ink-muted">
                            paired p10 to p90 {delta.range}
                          </span>
                        ) : null}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
