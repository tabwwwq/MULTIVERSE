import type { ValuationReport } from "@multiverse/contracts";
import { formatValue } from "@/results/format";

/*
 * Figures of the studio. Each states in words what it shows, labels its marks directly and has
 * a table next to it. Blue is the company as it stands, mint what adds, rose what takes away:
 * a sign is also written, so nothing depends on colour alone.
 */

const POSITIVE = "var(--color-series-alt-a)";
const NEGATIVE = "var(--color-negative)";
const NEUTRAL = "var(--color-series-baseline)";
const WIDTH = 640;
const LABEL = "fill-ink text-[12px]";
const MUTED = "fill-ink-muted text-[11px]";

const usd = (value: number, signed = false) => formatValue(value, "usd", { signed });

/** Explicit years and terminal value as parts of EV. */
export function CompositionBar({ explicit, terminal }: { explicit: number; terminal: number }) {
  const total = Math.abs(explicit) + Math.abs(terminal);
  const part = total > 0 ? (Math.abs(explicit) / total) * 100 : 0;
  return (
    <div>
      <div
        role="img"
        aria-label={`Present value of forecast quarters ${usd(explicit)}, of terminal value ${usd(terminal)}.`}
        className="flex h-3 gap-0.5 overflow-hidden rounded-pill"
      >
        <div style={{ width: `${part}%`, background: NEUTRAL }} />
        <div className="flex-1" style={{ background: POSITIVE }} />
      </div>
      <p className="mt-2 flex flex-wrap justify-between gap-x-4 text-small text-ink-muted tabular-nums">
        <span>Forecast quarters {usd(explicit)}</span>
        <span>Terminal value {usd(terminal)}</span>
      </p>
    </div>
  );
}

interface BridgeStep {
  label: string;
  value: number;
  total?: boolean;
}

/** EV down to equity value. EV and equity value are totals; the steps between them float. */
export function BridgeFigure({ steps }: { steps: readonly BridgeStep[] }) {
  const rowHeight = 34;
  const height = steps.length * rowHeight + 8;
  const left = 150;
  const right = 104;
  const plot = WIDTH - left - right;
  const bars = steps.reduce<(BridgeStep & { from: number; to: number })[]>((done, step) => {
    const before = done.at(-1)?.to ?? 0;
    const from = step.total ? 0 : before;
    const to = step.total ? step.value : before + step.value;
    return [...done, { ...step, from, to }];
  }, []);
  const values = bars.flatMap((bar) => [bar.from, bar.to, 0]);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const x = (value: number) => left + ((value - low) / Math.max(high - low, 1)) * plot;
  const words = steps.map((step) => `${step.label} ${usd(step.value, !step.total)}`).join(", ");
  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Bridge from enterprise value to equity value: ${words}.`}
    >
      {bars.map((bar, index) => {
        const y = index * rowHeight + 6;
        const start = Math.min(x(bar.from), x(bar.to));
        const width = Math.max(Math.abs(x(bar.to) - x(bar.from)), 2);
        const color = bar.total ? NEUTRAL : bar.value < 0 ? NEGATIVE : POSITIVE;
        return (
          <g key={bar.label}>
            <title>{`${bar.label}: ${usd(bar.value, !bar.total)}`}</title>
            <text x={left - 8} y={y + 15} textAnchor="end" className={LABEL}>
              {bar.label}
            </text>
            <rect x={start} y={y} width={width} height={22} rx={4} fill={color} />
            <text x={WIDTH - 4} y={y + 15} textAnchor="end" className={LABEL}>
              {usd(bar.value, !bar.total)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

type Tornado = ValuationReport["tornado"][number];

/** How far each driver moves EV, widest first, around the value of the central path. */
export function TornadoFigure({ rows, base }: { rows: readonly Tornado[]; base: number }) {
  const rowHeight = 56;
  const height = rows.length * rowHeight + 24;
  const left = 130;
  const right = 16;
  const plot = WIDTH - left - right;
  const spread = Math.max(
    ...rows.flatMap((row) => [
      Math.abs(Number(row.low_value) - base),
      Math.abs(Number(row.high_value) - base),
    ]),
    1,
  );
  const x = (value: number) => left + plot / 2 + ((value - base) / spread) * (plot / 2 - 64);
  const words = rows
    .map(
      (row) =>
        `${row.label}: ${usd(Number(row.low_value) - base, true)} to ${usd(Number(row.high_value) - base, true)}`,
    )
    .join("; ");
  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Change of enterprise value by driver. ${words}.`}
    >
      <line
        x1={x(base)}
        x2={x(base)}
        y1={0}
        y2={height - 20}
        stroke="var(--color-line-strong)"
        strokeWidth={1}
      />
      <text x={x(base)} y={height - 6} textAnchor="middle" className={MUTED}>
        Central path {usd(base)}
      </text>
      {rows.map((row, index) => {
        const low = Number(row.low_value);
        const high = Number(row.high_value);
        const y = index * rowHeight + 8;
        return (
          <g key={row.driver}>
            <title>{`${row.label}: ${row.low_label} ${usd(low - base, true)}, ${row.high_label} ${usd(high - base, true)}`}</title>
            <text x={left - 10} y={y + 15} textAnchor="end" className={LABEL}>
              {row.label}
            </text>
            <rect x={x(low)} y={y} width={x(base) - x(low)} height={20} rx={4} fill={NEGATIVE} />
            <rect
              x={x(base) + 2}
              y={y}
              width={Math.max(x(high) - x(base) - 2, 0)}
              height={20}
              rx={4}
              fill={POSITIVE}
            />
            <text x={x(low) - 6} y={y + 15} textAnchor="end" className={LABEL}>
              {usd(low - base, true)}
            </text>
            <text x={x(high) + 6} y={y + 15} className={LABEL}>
              {usd(high - base, true)}
            </text>
            <text x={x(base) - 6} y={y + 34} textAnchor="end" className={MUTED}>
              {row.low_label}
            </text>
            <text x={x(base) + 8} y={y + 34} className={MUTED}>
              {row.high_label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

type Scenario = ValuationReport["scenarios"][number];

/** p10 to p90 of EV in each scenario, with the median as a dot. */
export function ScenarioFigure({ rows }: { rows: readonly Scenario[] }) {
  const rowHeight = 48;
  const height = rows.length * rowHeight + 12;
  const left = 70;
  const right = 96;
  const plot = WIDTH - left - right;
  const low = Math.min(...rows.map((row) => Number(row.ev_p10)));
  const high = Math.max(...rows.map((row) => Number(row.ev_p90)));
  const x = (value: number) => left + ((value - low) / Math.max(high - low, 1)) * plot;
  const words = rows
    .map(
      (row) =>
        `${row.label}: median ${usd(Number(row.ev_p50))}, p10 ${usd(Number(row.ev_p10))}, p90 ${usd(Number(row.ev_p90))}`,
    )
    .join("; ");
  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Enterprise value by scenario, conditional on the assumed model. ${words}.`}
    >
      {rows.map((row, index) => {
        const y = index * rowHeight + 22;
        const p10 = Number(row.ev_p10);
        const p50 = Number(row.ev_p50);
        const p90 = Number(row.ev_p90);
        return (
          <g key={row.scenario}>
            <title>{`${row.label}: p10 ${usd(p10)}, p50 ${usd(p50)}, p90 ${usd(p90)}`}</title>
            <text x={left - 10} y={y + 4} textAnchor="end" className={LABEL}>
              {row.label}
            </text>
            <line
              x1={x(p10)}
              x2={x(p90)}
              y1={y}
              y2={y}
              stroke={NEUTRAL}
              strokeWidth={6}
              strokeLinecap="round"
            />
            <circle
              cx={x(p50)}
              cy={y}
              r={7}
              fill={POSITIVE}
              stroke="var(--color-surface)"
              strokeWidth={2}
            />
            <text x={x(p50)} y={y - 12} textAnchor="middle" className={LABEL}>
              {usd(p50)}
            </text>
            <text x={x(p10)} y={y + 18} textAnchor="middle" className={MUTED}>
              {usd(p10)}
            </text>
            <text x={x(p90)} y={y + 18} textAnchor="middle" className={MUTED}>
              {usd(p90)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
