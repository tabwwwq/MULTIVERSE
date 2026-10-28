"use client";

import type { TimelineEvent } from "@multiverse/contracts";
import {
  type KeyboardEvent,
  type RefObject,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { LineKey, SERIES_STYLE } from "@/components/results/series-style";
import { formatTick } from "@/results/format";
import { linear } from "@/results/scale";
import {
  type ChartModel,
  type ChartPoint,
  type ChartSeries,
  pointText,
  type SeriesKey,
} from "@/results/series";

/*
 * Timeline chart in plain SVG (docs/10 chart grammar, dataviz guidance): 2px lines,
 * p10-p90 bands as a 12% wash, solid hairline grid, a crosshair that snaps to the
 * nearest quarter and one tooltip listing every visible series. The same readout is
 * reachable with the arrow keys and is announced to screen readers; the table view
 * holds every number without hovering.
 */

const MARGIN = { top: 28, right: 16, bottom: 40, left: 64 };

interface TimelineChartProps {
  model: ChartModel;
  visible: ReadonlySet<SeriesKey>;
  showBands: boolean;
  events: readonly TimelineEvent[];
  labelledBy: string;
  describedBy: string;
}

function shortLabel(label: string): string {
  // "FY2022 Q3" -> "Q3 FY22"
  const match = /^FY(\d{4}) (Q\d)$/.exec(label);
  return match ? `${match[2]} FY${match[1]?.slice(2)}` : label;
}

function useWidth(fallback: number): [RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? fallback);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [fallback]);
  return [ref, width];
}

export function TimelineChart({
  model,
  visible,
  showBands,
  events,
  labelledBy,
  describedBy,
}: TimelineChartProps) {
  const [containerRef, width] = useWidth(720);
  const [active, setActive] = useState<number | null>(null);
  const helpId = useId();
  const compact = width < 520;
  const height = compact ? 280 : 340;
  const plotWidth = Math.max(10, width - MARGIN.left - MARGIN.right);
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const quarters = useMemo(() => {
    const byEnd = new Map<string, string>();
    for (const series of model.series)
      for (const point of series.points) byEnd.set(point.end, point.label);
    return [...byEnd.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([end, label]) => ({ end, label }));
  }, [model]);
  const index = useMemo(() => new Map(quarters.map((quarter, i) => [quarter.end, i])), [quarters]);

  const x = linear([0, Math.max(1, quarters.length - 1)], [0, plotWidth]);
  const y = linear([model.axis.min, model.axis.max], [plotHeight, 0]);
  const shown = model.series.filter((series) => visible.has(series.key));
  const signed = model.mode !== "absolute";
  const firstForecast = quarters.findIndex(
    (quarter) => model.lastObserved !== null && quarter.end > model.lastObserved,
  );
  const observed = model.series.find((series) => series.key === "observed");
  const lastObservedPoint = observed?.points.at(-1);

  const linePath = (series: ChartSeries) => {
    const points = [...series.points];
    // Join each absolute forecast to the last reported quarter so the paths read as one timeline.
    if (
      series.kind === "forecast" &&
      model.mode === "absolute" &&
      lastObservedPoint &&
      visible.has("observed")
    ) {
      points.unshift(lastObservedPoint);
    }
    return points
      .map(
        (point, i) =>
          `${i === 0 ? "M" : "L"}${x(index.get(point.end) ?? 0).toFixed(1)},${y(point.p50).toFixed(1)}`,
      )
      .join(" ");
  };
  const bandPath = (series: ChartSeries) => {
    const top = series.points.map(
      (p) => `${x(index.get(p.end) ?? 0).toFixed(1)},${y(p.p90).toFixed(1)}`,
    );
    const bottom = [...series.points]
      .reverse()
      .map((p) => `${x(index.get(p.end) ?? 0).toFixed(1)},${y(p.p10).toFixed(1)}`);
    return `M${top.join(" L")} L${bottom.join(" L")} Z`;
  };

  // Event dates fall between quarter ends: place them proportionally.
  const dateX = (date: string): number | null => {
    const after = quarters.findIndex((quarter) => quarter.end >= date);
    if (after <= 0) return after === 0 ? x(0) : null;
    const prev = quarters[after - 1];
    const next = quarters[after];
    if (!prev || !next) return null;
    const span = Date.parse(next.end) - Date.parse(prev.end);
    const share = (Date.parse(date) - Date.parse(prev.end)) / span;
    return x(after - 1 + share);
  };
  const effectiveDates = [
    ...new Set(events.filter((e) => e.kind === "effective").map((e) => e.on)),
  ];

  // About 72px per quarter label, so labels never touch on a 390px screen.
  const step = Math.max(1, Math.ceil(quarters.length / Math.max(2, Math.floor(plotWidth / 72))));
  const activeQuarter = active === null ? null : quarters[active];
  const rows = activeQuarter
    ? shown
        .map((series) => ({
          series,
          point: series.points.find((p) => p.end === activeQuarter.end),
        }))
        .filter((row): row is { series: ChartSeries; point: ChartPoint } => row.point !== undefined)
    : [];
  const readout = activeQuarter
    ? `${activeQuarter.label}. ${rows
        .map(({ series, point }) => `${series.label}: ${pointText(point, model.unit, signed)}`)
        .join(". ")}`
    : "";

  const moveTo = (next: number) => setActive(Math.max(0, Math.min(quarters.length - 1, next)));
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, () => void> = {
      ArrowRight: () => moveTo((active ?? -1) + 1),
      ArrowLeft: () => moveTo((active ?? quarters.length) - 1),
      Home: () => moveTo(0),
      End: () => moveTo(quarters.length - 1),
      Escape: () => setActive(null),
    };
    const action = keys[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  };
  const onPointer = (clientX: number, element: SVGRectElement) => {
    const box = element.getBoundingClientRect();
    const share = (clientX - box.left) / Math.max(1, box.width);
    moveTo(Math.round(share * (quarters.length - 1)));
  };

  const tooltipLeft = activeQuarter ? MARGIN.left + x(active ?? 0) : 0;
  const tooltipOnLeft = tooltipLeft > width / 2;

  return (
    <div ref={containerRef} className="relative w-full">
      <div
        role="group"
        tabIndex={0}
        aria-labelledby={labelledBy}
        aria-describedby={`${describedBy} ${helpId}`}
        onKeyDown={onKeyDown}
        onBlur={() => setActive(null)}
        className="rounded-panel focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-mint"
      >
        <div className="flex justify-end">
          <span className="chart-watermark" aria-hidden="true">
            Synthetic · mock
          </span>
        </div>
        <svg
          width={width}
          height={height}
          role="presentation"
          className="block"
          data-testid="timeline-svg"
        >
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {firstForecast > 0 ? (
              <g>
                <rect
                  x={(x(firstForecast - 1) + x(firstForecast)) / 2}
                  y={0}
                  width={plotWidth - (x(firstForecast - 1) + x(firstForecast)) / 2}
                  height={plotHeight}
                  fill="var(--color-inset)"
                  opacity="0.55"
                />
                <text x={4} y={-10} className="chart-label">
                  History (reported)
                </text>
                <text
                  x={(x(firstForecast - 1) + x(firstForecast)) / 2 + 4}
                  y={-10}
                  className="chart-label"
                >
                  Forecast (mock)
                </text>
              </g>
            ) : null}
            {model.axis.ticks.map((tick) => (
              <g key={tick}>
                <line
                  x1={0}
                  x2={plotWidth}
                  y1={y(tick)}
                  y2={y(tick)}
                  stroke={tick === 0 ? "var(--color-line-strong)" : "var(--color-line)"}
                  strokeWidth="1"
                />
                <text
                  x={-8}
                  y={y(tick)}
                  dy="0.32em"
                  textAnchor="end"
                  className="chart-label tabular-nums"
                >
                  {formatTick(tick, model.unit, signed)}
                </text>
              </g>
            ))}
            {quarters.map((quarter, i) =>
              i % step === 0 ? (
                <text
                  key={quarter.end}
                  x={x(i)}
                  y={plotHeight + 22}
                  textAnchor={x(i) > plotWidth - 30 ? "end" : x(i) < 30 ? "start" : "middle"}
                  className="chart-label"
                >
                  {shortLabel(quarter.label)}
                </text>
              ) : null,
            )}
            {effectiveDates.map((date) => {
              const position = dateX(date);
              return position === null ? null : (
                <g key={date}>
                  <line
                    x1={position}
                    x2={position}
                    y1={0}
                    y2={plotHeight}
                    stroke="var(--color-ink-muted)"
                    strokeWidth="1"
                    strokeDasharray="2 3"
                  />
                  <text x={position + 4} y={12} className="chart-label">
                    Decision
                  </text>
                </g>
              );
            })}
            {showBands
              ? shown
                  .filter(
                    (series) =>
                      series.kind === "forecast" && series.points.some((p) => p.p10 !== p.p90),
                  )
                  .map((series) => (
                    <path
                      key={`band-${series.key}`}
                      d={bandPath(series)}
                      fill={SERIES_STYLE[series.key].color}
                      opacity="0.12"
                      data-testid={`band-${series.key}`}
                    />
                  ))
              : null}
            {shown.map((series) => (
              <path
                key={series.key}
                d={linePath(series)}
                fill="none"
                stroke={SERIES_STYLE[series.key].color}
                strokeWidth="2"
                strokeDasharray={SERIES_STYLE[series.key].dash}
                strokeLinecap="round"
                strokeLinejoin="round"
                data-testid={`line-${series.key}`}
              />
            ))}
            {activeQuarter ? (
              <g>
                <line
                  x1={x(active ?? 0)}
                  x2={x(active ?? 0)}
                  y1={0}
                  y2={plotHeight}
                  stroke="var(--color-ink-muted)"
                  strokeWidth="1"
                />
                {rows.map(({ series, point }) => (
                  <circle
                    key={series.key}
                    cx={x(active ?? 0)}
                    cy={y(point.p50)}
                    r="4.5"
                    fill={SERIES_STYLE[series.key].color}
                    stroke="var(--color-surface)"
                    strokeWidth="2"
                  />
                ))}
              </g>
            ) : null}
            <rect
              x={0}
              y={0}
              width={plotWidth}
              height={plotHeight}
              fill="transparent"
              onPointerMove={(event) => onPointer(event.clientX, event.currentTarget)}
              onPointerDown={(event) => onPointer(event.clientX, event.currentTarget)}
              onPointerLeave={() => setActive(null)}
            />
          </g>
        </svg>
      </div>
      <p id={helpId} className="sr-only">
        Use the left and right arrow keys to read each quarter.
      </p>
      <p className="sr-only" aria-live="polite">
        {readout}
      </p>
      {activeQuarter && rows.length > 0 ? (
        <div
          role="presentation"
          className="chart-tooltip"
          style={{
            top: MARGIN.top,
            ...(tooltipOnLeft ? { right: width - tooltipLeft + 12 } : { left: tooltipLeft + 12 }),
          }}
          data-testid="chart-tooltip"
        >
          <p className="text-small font-medium text-ink">{activeQuarter.label}</p>
          <p className="text-micro text-ink-muted">
            {rows[0]?.series.kind === "observed"
              ? "Reported, public by the cutoff"
              : "Mock quantiles p10 to p90"}
          </p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {rows.map(({ series, point }) => (
              <li key={series.key} className="flex flex-col">
                <span className="text-small font-medium text-ink tabular-nums">
                  {pointText(point, model.unit, signed)}
                </span>
                <span className="flex items-center gap-2 text-micro text-ink-muted">
                  <LineKey series={series.key} width={16} />
                  {series.label}
                  {point.source
                    ? ` · source ${point.source.id}, filed ${point.source.filedAt}`
                    : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
