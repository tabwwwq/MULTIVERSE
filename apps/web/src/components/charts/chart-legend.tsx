/*
 * Chart grammar (docs/10): observed solid grey-blue, baseline dashed blue,
 * alternate A solid mint, alternate B solid violet, quantile band translucent,
 * vertical decision marker. Line style differs as well as colour, so the series
 * stay distinguishable without colour vision.
 */

export const SERIES = [
  { id: "observed", label: "Observed history", stroke: "var(--color-observed)", dash: undefined },
  { id: "baseline", label: "Baseline forecast", stroke: "var(--color-blue)", dash: "6 5" },
  { id: "alt-a", label: "Alternate A", stroke: "var(--color-mint)", dash: undefined },
  { id: "alt-b", label: "Alternate B", stroke: "var(--color-violet)", dash: "2 4" },
] as const;

function Swatch({ stroke, dash }: { stroke: string; dash: string | undefined }) {
  return (
    <svg width="32" height="10" viewBox="0 0 32 10" aria-hidden="true" className="shrink-0">
      <line
        x1="1"
        y1="5"
        x2="31"
        y2="5"
        stroke={stroke}
        strokeWidth="2.5"
        strokeDasharray={dash}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function ChartLegend() {
  return (
    <ul
      className="flex flex-wrap gap-x-6 gap-y-2 text-small text-ink-muted"
      aria-label="Chart legend"
    >
      {SERIES.map((series) => (
        <li key={series.id} className="flex items-center gap-2">
          <Swatch stroke={series.stroke} dash={series.dash} />
          {series.label}
        </li>
      ))}
      <li className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="h-2.5 w-8 rounded-pill bg-mint/20 ring-1 ring-mint/40"
        />
        p10 to p90 band (conditional model quantiles)
      </li>
      <li className="flex items-center gap-2">
        <svg width="10" height="16" viewBox="0 0 10 16" aria-hidden="true" className="shrink-0">
          <line
            x1="5"
            y1="1"
            x2="5"
            y2="15"
            stroke="var(--color-ink-muted)"
            strokeWidth="1.5"
            strokeDasharray="2 2"
          />
        </svg>
        Decision date
      </li>
    </ul>
  );
}
