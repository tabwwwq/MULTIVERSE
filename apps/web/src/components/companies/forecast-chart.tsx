import type { CompanyDossier, RealCompany } from "@multiverse/contracts";

type Forecast = NonNullable<RealCompany["forecast"]>;
type Band = Forecast["bands"][number];

/** Columns of the seven levels: 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95. */
const P10 = 1;
const P50 = 3;
const P90 = 5;
const WIDTH = 460;
const HEIGHT = 200;
const PAD = { left: 44, right: 12, top: 12, bottom: 26 };

interface Point {
  /** Quarters from the first observed quarter of the chart. */
  x: number;
  y: number;
}

interface Series {
  observed: Point[];
  forecast: { x: number; low: number; middle: number; high: number; label: string }[];
  ticks: { x: number; label: string }[];
}

function quarterIndex(day: string): number {
  return Number(day.slice(0, 4)) * 4 + Math.ceil(Number(day.slice(5, 7)) / 3);
}

function label(index: number): string {
  const year = Math.floor((index - 1) / 4);
  const quarter = ((index - 1) % 4) + 1;
  return `${year} Q${quarter}`;
}

function byQuarter(dossier: CompanyDossier, metric: string): Map<number, number> {
  const found = new Map<number, number>();
  for (const value of dossier.values) {
    if (value.metric === metric && value.quantity) {
      found.set(quarterIndex(value.period.end_date), Number(value.quantity.value));
    }
  }
  return found;
}

function observedGrowth(dossier: CompanyDossier): Map<number, number> {
  const revenue = byQuarter(dossier, "revenue");
  const found = new Map<number, number>();
  for (const [quarter, now] of revenue) {
    const before = revenue.get(quarter - 4);
    if (before !== undefined && now + before !== 0) {
      found.set(quarter, (now - before) / ((now + before) / 2));
    }
  }
  return found;
}

function observedMargin(dossier: CompanyDossier): Map<number, number> {
  const revenue = byQuarter(dossier, "revenue");
  const found = new Map<number, number>();
  for (const [quarter, ebitda] of byQuarter(dossier, "ebitda_calculated")) {
    const sales = revenue.get(quarter);
    if (sales) found.set(quarter, ebitda / sales);
  }
  return found;
}

function seriesOf(observed: Map<number, number>, bands: readonly Band[]): Series {
  const quarters = [...observed.keys()].sort((a, b) => a - b);
  const first = quarters[0] ?? 0;
  const forecast = bands
    .filter((band) => band.horizon <= 12)
    .map((band) => {
      const index = quarterIndex(band.quarter_end);
      return {
        x: index - first,
        low: band.values[P10] ?? 0,
        middle: band.values[P50] ?? 0,
        high: band.values[P90] ?? 0,
        label: label(index),
      };
    });
  const ticks = [
    { x: 0, label: label(first) },
    ...forecast.slice(-1).map((point) => ({ x: point.x, label: point.label })),
  ];
  return {
    observed: quarters.map((quarter) => ({ x: quarter - first, y: observed.get(quarter) ?? 0 })),
    forecast,
    ticks,
  };
}

function Panel({ title, series }: { title: string; series: Series }) {
  const values = [
    ...series.observed.map((point) => point.y),
    ...series.forecast.flatMap((point) => [point.low, point.high]),
  ];
  if (values.length === 0 || series.forecast.length === 0) return null;
  const top = Math.max(...values, 0);
  const bottom = Math.min(...values, 0);
  const span = top - bottom || 1;
  const last = Math.max(...series.forecast.map((point) => point.x), 1);
  const px = (x: number) => PAD.left + (x / last) * (WIDTH - PAD.left - PAD.right);
  const py = (y: number) => PAD.top + ((top - y) / span) * (HEIGHT - PAD.top - PAD.bottom);
  const line = (points: Point[]) => points.map((p) => `${px(p.x)},${py(p.y)}`).join(" ");
  const start = series.observed.at(-1);
  const fan = [
    ...(start ? [{ x: start.x, y: start.y }] : []),
    ...series.forecast.map((point) => ({ x: point.x, y: point.high })),
    ...[...series.forecast].reverse().map((point) => ({ x: point.x, y: point.low })),
  ];
  const middle = [
    ...(start ? [start] : []),
    ...series.forecast.map((point) => ({ x: point.x, y: point.middle })),
  ];
  const percent = (value: number) => `${(100 * value).toFixed(0)}%`;
  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <figcaption className="text-small font-medium text-ink">{title}</figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${title}: observed quarters, then the model's range from p10 to p90. The table below has the values.`}
        className="w-full"
      >
        <line
          x1={PAD.left}
          x2={WIDTH - PAD.right}
          y1={py(0)}
          y2={py(0)}
          className="stroke-line-strong"
        />
        <text
          x={PAD.left - 6}
          y={py(top) + 4}
          textAnchor="end"
          className="fill-ink-muted text-[11px]"
        >
          {percent(top)}
        </text>
        <text
          x={PAD.left - 6}
          y={py(bottom) + 4}
          textAnchor="end"
          className="fill-ink-muted text-[11px]"
        >
          {percent(bottom)}
        </text>
        {series.ticks.map((tick) => (
          <text
            key={tick.label}
            x={px(tick.x)}
            y={HEIGHT - 8}
            textAnchor={tick.x === 0 ? "start" : "end"}
            className="fill-ink-muted text-[11px]"
          >
            {tick.label}
          </text>
        ))}
        <polygon points={line(fan)} className="fill-blue/20 stroke-none" />
        <polyline
          points={line(middle)}
          fill="none"
          strokeWidth="2"
          strokeDasharray="5 4"
          className="stroke-blue"
        />
        <polyline
          points={line(series.observed)}
          fill="none"
          strokeWidth="2"
          className="stroke-mint"
        />
      </svg>
    </figure>
  );
}

/** Solid line: what the filings say. Dashed line and band: the model's p50 and p10 to p90. */
export function ForecastChart({
  dossier,
  forecast,
}: {
  dossier: CompanyDossier;
  forecast: Forecast;
}) {
  const growth = forecast.bands.filter((band) => band.target === "revenue_growth");
  const margin = forecast.bands.filter((band) => band.target === "ebitda_margin");
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {growth.length > 0 ? (
        <Panel
          title="Revenue growth over a year"
          series={seriesOf(observedGrowth(dossier), growth)}
        />
      ) : null}
      {margin.length > 0 ? (
        <Panel title="EBITDA margin" series={seriesOf(observedMargin(dossier), margin)} />
      ) : null}
    </div>
  );
}
