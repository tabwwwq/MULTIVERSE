import type {
  ChangeDistribution,
  ScenarioResult,
  TimelineEvent,
  Waterfall,
} from "@multiverse/contracts";
import { LineKey, SERIES_STYLE } from "@/components/results/series-style";
import { formatTick, formatValue } from "@/results/format";
import { axisFor, linear } from "@/results/scale";
import { scenarioLabel } from "@/results/series";

/*
 * Static figures of a result: the distribution of paired differences, the waterfall
 * from baseline to alternate, and the event timeline. Each figure states what it shows
 * in words, labels its bars directly, and keeps a table of every value.
 */

const METRIC_LABELS: Record<string, string> = {
  revenue: "Revenue",
  ebitda: "EBITDA (calculated)",
  fcf: "FCF (CFO − CAPEX)",
  net_debt: "Net debt",
  ev: "EV (mock)",
};

// A narrow canvas: figures scale to their column, so text stays readable on a 390px screen.
const WIDTH = 400;
const HEIGHT = 230;
const PAD = { top: 16, right: 12, bottom: 48, left: 44 };

export function DistributionFigure({
  distribution,
  result,
}: {
  distribution: ChangeDistribution;
  result: ScenarioResult;
}) {
  const label = scenarioLabel(result, distribution.scenario);
  const metric = METRIC_LABELS[distribution.metric] ?? distribution.metric;
  const counts = distribution.bins.map((bin) => bin.count);
  const low = Number(distribution.bins[0]?.low ?? 0);
  const high = Number(distribution.bins.at(-1)?.high ?? 1);
  const xDomain: [number, number] = [Math.min(low, 0), Math.max(high, 0)];
  const plotW = WIDTH - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = linear(xDomain, [0, plotW]);
  const yAxis = axisFor(counts, "include_zero", 4);
  const y = linear([0, yAxis.max], [plotH, 0]);
  const xTicks = axisFor([xDomain[0], xDomain[1]], "include_zero", 4).ticks.filter(
    (tick) => tick >= xDomain[0] && tick <= xDomain[1],
  );
  const probability = `${Math.round(Number(distribution.probability_above_zero) * 100)}%`;
  const titleId = `dist-${distribution.scenario}-${distribution.metric}`;

  return (
    <figure
      aria-labelledby={titleId}
      className="flex flex-col gap-2 rounded-panel border border-line bg-surface p-4"
    >
      <figcaption id={titleId} className="flex flex-col gap-1">
        <span className="flex items-center gap-2 font-medium text-ink">
          <LineKey series={distribution.scenario} width={16} />
          {metric}: {label} minus baseline at {distribution.period_end}
        </span>
        <span className="text-small text-ink-muted">
          Paired differences across {result.paths} mock paths. Mean{" "}
          {formatValue(Number(distribution.mean), "usd", { signed: true })}. The alternate is above
          the baseline on {probability} of paths under the mock model, not validated.
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Histogram of ${metric} differences for ${label}. ${probability} of paths above zero.`}
      >
        <g transform={`translate(${PAD.left},${PAD.top})`}>
          {yAxis.ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={0}
                x2={plotW}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--color-line)"
                strokeWidth="1"
              />
              <text
                x={-8}
                y={y(tick)}
                dy="0.32em"
                textAnchor="end"
                className="figure-label tabular-nums"
              >
                {tick}
              </text>
            </g>
          ))}
          {distribution.bins.map((bin) => {
            const left = x(Number(bin.low));
            const right = x(Number(bin.high));
            const barWidth = Math.max(1, right - left - 2);
            return (
              <rect
                key={bin.low}
                x={left + 1}
                y={y(bin.count)}
                width={barWidth}
                height={Math.max(0, plotH - y(bin.count))}
                rx={Math.min(2, barWidth / 2)}
                fill={SERIES_STYLE[distribution.scenario].color}
                opacity="0.85"
              >
                <title>{`${formatValue(Number(bin.low), "usd", { signed: true })} to ${formatValue(Number(bin.high), "usd", { signed: true })}: ${bin.count} paths`}</title>
              </rect>
            );
          })}
          <line x1={x(0)} x2={x(0)} y1={0} y2={plotH} stroke="var(--color-ink)" strokeWidth="1.5" />
          <text
            x={x(0) > plotW - 72 ? x(0) - 4 : x(0) + 4}
            y={10}
            textAnchor={x(0) > plotW - 72 ? "end" : "start"}
            className="figure-label"
          >
            Baseline
          </text>
          {xTicks.map((tick) => (
            <text
              key={tick}
              x={x(tick)}
              y={plotH + 20}
              textAnchor={x(tick) > plotW - 24 ? "end" : x(tick) < 24 ? "start" : "middle"}
              className="figure-label tabular-nums"
            >
              {formatTick(tick, "usd", true)}
            </text>
          ))}
          <text x={plotW / 2} y={plotH + 42} textAnchor="middle" className="figure-label">
            Difference in USD · paths per bin
          </text>
        </g>
      </svg>
      <details className="text-small text-ink-muted">
        <summary className="cursor-pointer text-ink">Bins as a table</summary>
        <table className="mt-2 w-full text-left tabular-nums">
          <caption className="sr-only">{`Histogram bins of ${metric} differences for ${label}`}</caption>
          <thead>
            <tr>
              <th scope="col" className="py-1 pr-4 font-medium text-ink">
                Difference
              </th>
              <th scope="col" className="py-1 font-medium text-ink">
                Paths
              </th>
            </tr>
          </thead>
          <tbody>
            {distribution.bins.map((bin) => (
              <tr key={bin.low}>
                <td className="py-0.5 pr-4">
                  {formatValue(Number(bin.low), "usd", { signed: true })} to{" "}
                  {formatValue(Number(bin.high), "usd", { signed: true })}
                </td>
                <td className="py-0.5">{bin.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

export function WaterfallFigure({
  waterfall,
  result,
}: {
  waterfall: Waterfall;
  result: ScenarioResult;
}) {
  const label = scenarioLabel(result, waterfall.scenario);
  const metric = METRIC_LABELS[waterfall.metric] ?? waterfall.metric;
  const what =
    waterfall.aggregation === "cumulative"
      ? `cumulative ${metric} up to ${waterfall.period_end}`
      : `${metric} in the quarter ending ${waterfall.period_end}`;
  type Bar = {
    label: string;
    from: number;
    to: number;
    kind: "total" | "step";
    scenario: "baseline" | "alt_a" | "alt_b";
  };
  const bars: Bar[] = [];
  let running = Number(waterfall.start);
  bars.push({ label: "Baseline", from: 0, to: running, kind: "total", scenario: "baseline" });
  for (const step of waterfall.steps) {
    const next = running + Number(step.value);
    bars.push({
      label: step.label,
      from: running,
      to: next,
      kind: "step",
      scenario: waterfall.scenario,
    });
    running = next;
  }
  bars.push({
    label,
    from: 0,
    to: Number(waterfall.end),
    kind: "total",
    scenario: waterfall.scenario,
  });

  // Each row: the label and value on one line, the bar below, over the full width.
  const rowH = 52;
  const height = bars.length * rowH + 28;
  const plotW = WIDTH - 16;
  const axis = axisFor(
    bars.flatMap((bar) => [bar.from, bar.to]),
    "include_zero",
    3,
  );
  const x = linear([axis.min, axis.max], [8, 8 + plotW]);
  const titleId = `wf-${waterfall.scenario}`;

  return (
    <figure
      aria-labelledby={titleId}
      className="flex flex-col gap-2 rounded-panel border border-line bg-surface p-4"
    >
      <figcaption id={titleId} className="flex flex-col gap-1">
        <span className="flex items-center gap-2 font-medium text-ink">
          <LineKey series={waterfall.scenario} width={16} />
          From baseline to {label}: {what}
        </span>
        <span className="text-small text-ink-muted">
          Means across paired mock paths: means add up, medians do not. The steps sum exactly to the
          difference.
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Waterfall from baseline to ${label}. Baseline ${formatValue(Number(waterfall.start), "usd")}, ${label} ${formatValue(Number(waterfall.end), "usd")}.`}
      >
        {bars.map((bar, i) => {
          const top = 8 + i * rowH;
          const left = x(Math.min(bar.from, bar.to));
          const width = Math.max(2, Math.abs(x(bar.to) - x(bar.from)));
          const value = bar.kind === "total" ? bar.to : bar.to - bar.from;
          return (
            <g key={bar.label} transform={`translate(0,${top})`}>
              <text x={8} y={14} className="figure-label-strong">
                {bar.label}
              </text>
              <text
                x={WIDTH - 8}
                y={14}
                textAnchor="end"
                className="figure-label-strong tabular-nums"
              >
                {formatValue(value, "usd", { signed: bar.kind === "step" })}
              </text>
              <rect
                x={left}
                y={22}
                width={width}
                height={20}
                rx="3"
                fill={SERIES_STYLE[bar.scenario].color}
                opacity={bar.kind === "total" ? 0.9 : 0.55}
              />
            </g>
          );
        })}
        <line
          x1={x(0)}
          x2={x(0)}
          y1={4}
          y2={height - 24}
          stroke="var(--color-line-strong)"
          strokeWidth="1"
        />
        {axis.ticks.map((tick) => (
          <text
            key={tick}
            x={x(tick)}
            y={height - 6}
            textAnchor={x(tick) > WIDTH - 40 ? "end" : x(tick) < 40 ? "start" : "middle"}
            className="figure-label tabular-nums"
          >
            {formatTick(tick, "usd", false)}
          </text>
        ))}
      </svg>
      <ul className="flex flex-col gap-1 text-small text-ink-muted">
        {waterfall.steps.map((step) => (
          <li key={step.label}>
            <span className="text-ink">{step.label}:</span> {step.explanation}
          </li>
        ))}
      </ul>
    </figure>
  );
}

const EVENT_KINDS: Record<TimelineEvent["kind"], string> = {
  cutoff: "Cutoff",
  announcement: "Announced",
  effective: "Takes effect",
  effect_start: "Effect starts",
  full_effect: "Full effect",
};

export function EventTimeline({ events }: { events: readonly TimelineEvent[] }) {
  const ordered = [...events].sort(
    (a, b) => a.on.localeCompare(b.on) || a.label.localeCompare(b.label),
  );
  return (
    <ol className="flex flex-col border-l border-line-strong pl-5">
      {ordered.map((event) => (
        <li key={`${event.on}-${event.label}`} className="relative pb-4 last:pb-0">
          <span
            aria-hidden="true"
            className="absolute top-1.5 -left-[1.6rem] size-2.5 rounded-full border-2 border-surface"
            style={{
              background: event.scenario
                ? SERIES_STYLE[event.scenario].color
                : "var(--color-ink-muted)",
            }}
          />
          <p className="text-small text-ink">
            <time dateTime={event.on} className="tabular-nums">
              {event.on}
            </time>{" "}
            · {EVENT_KINDS[event.kind]}
          </p>
          <p className="flex items-center gap-2 text-small text-ink-muted">
            {event.scenario ? <LineKey series={event.scenario} width={16} /> : null}
            {event.label}
          </p>
        </li>
      ))}
    </ol>
  );
}
