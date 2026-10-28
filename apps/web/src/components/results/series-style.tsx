import type { SeriesKey } from "@/results/series";

/*
 * Chart grammar (docs/10): observed solid cool grey-blue, baseline dashed blue, the
 * first alternate solid mint, the second violet. Each series also has its own dash
 * pattern, so identity never relies on colour alone. Colour follows the series, never
 * its position: hiding one series does not repaint the others.
 */

export const SERIES_STYLE: Record<SeriesKey, { color: string; dash: string | undefined }> = {
  observed: { color: "var(--color-observed)", dash: undefined },
  baseline: { color: "var(--color-series-baseline)", dash: "6 5" },
  alt_a: { color: "var(--color-series-alt-a)", dash: undefined },
  alt_b: { color: "var(--color-series-alt-b)", dash: "2 4" },
};

/** Short stroke of the series colour and dash, used in legends, tooltips and tables. */
export function LineKey({ series, width = 24 }: { series: SeriesKey; width?: number }) {
  const style = SERIES_STYLE[series];
  return (
    <svg
      width={width}
      height="10"
      viewBox={`0 0 ${width} 10`}
      aria-hidden="true"
      className="shrink-0"
    >
      <line
        x1="1"
        y1="5"
        x2={width - 1}
        y2="5"
        stroke={style.color}
        strokeWidth="2.5"
        strokeDasharray={style.dash}
        strokeLinecap="round"
      />
    </svg>
  );
}
