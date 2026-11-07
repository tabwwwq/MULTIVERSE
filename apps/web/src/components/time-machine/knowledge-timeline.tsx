import type { Comparison, Knowledge } from "@/time-machine/compare";

const WIDTH = 880;
const ROW = 26;
const PAD = { left: 104, right: 24, top: 52, bottom: 40 };

export const KNOWLEDGE_LABELS: Record<Knowledge, string> = {
  known_at_first: "Public at the first date",
  new_in_between: "Became public in between",
  not_yet: "Not public at the second date",
};

const COLOURS: Record<Knowledge, string> = {
  known_at_first: "var(--color-mint)",
  new_in_between: "var(--color-violet)",
  not_yet: "var(--color-line-strong)",
};

function days(day: string): number {
  return Date.parse(`${day}T00:00:00Z`) / 86_400_000;
}

/**
 * One line per quarter, from the end of its period to the day its filing was published. The
 * two cutoffs are vertical lines: what lies left of a line was public on that day.
 */
export function KnowledgeTimeline({ comparison }: { comparison: Comparison }) {
  const { quarters, first, second } = comparison;
  const height = PAD.top + ROW * quarters.length + PAD.bottom;
  const points = quarters.flatMap((quarter) => [quarter.endDate, quarter.filedAt ?? second]);
  const start = Math.min(...points.map(days), days(first)) - 20;
  const end = Math.max(...points.map(days), days(second)) + 20;
  const x = (day: string) =>
    PAD.left + ((days(day) - start) / (end - start)) * (WIDTH - PAD.left - PAD.right);
  const years: string[] = [];
  for (let year = Number(new Date(start * 86_400_000).getUTCFullYear()) + 1; ; year += 1) {
    const day = `${year}-01-01`;
    if (days(day) > end) break;
    years.push(day);
  }
  const description = `${quarters.length} quarters. ${comparison.knownAtFirst} were public on ${first}, ${comparison.newInBetween} became public by ${second}, ${comparison.notYet} were still not public on ${second}.`;

  return (
    <figure className="flex flex-col gap-3">
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label="From the end of each quarter to the day it became public"
        aria-describedby="timeline-desc"
      >
        <title id="timeline-title">From the end of each quarter to the day it became public</title>
        <desc id="timeline-desc">{description}</desc>
        {years.map((day) => (
          <g key={day}>
            <line
              x1={x(day)}
              x2={x(day)}
              y1={PAD.top - 8}
              y2={height - PAD.bottom}
              stroke="var(--color-line)"
              strokeWidth={1}
            />
            <text
              x={x(day)}
              y={height - PAD.bottom + 20}
              textAnchor="middle"
              className="figure-label"
            >
              {day.slice(0, 4)}
            </text>
          </g>
        ))}
        {[
          { day: first, label: `First date ${first}` },
          { day: second, label: `Second date ${second}` },
        ].map((cutoff, index) => (
          <g key={cutoff.day}>
            <line
              x1={x(cutoff.day)}
              x2={x(cutoff.day)}
              y1={index === 0 ? 4 : 20}
              y2={height - PAD.bottom}
              stroke="var(--color-ink)"
              strokeWidth={1.5}
              strokeDasharray={index === 0 ? "4 4" : undefined}
            />
            <text
              x={x(cutoff.day)}
              y={index === 0 ? 14 : 30}
              textAnchor="end"
              dx={-6}
              className="figure-label-strong"
            >
              {cutoff.label}
            </text>
          </g>
        ))}
        {quarters.map((quarter, index) => {
          const y = PAD.top + ROW * index + ROW / 2;
          const colour = COLOURS[quarter.knowledge];
          const filed = quarter.filedAt ?? second;
          return (
            <g key={quarter.key}>
              <text x={PAD.left - 12} y={y + 4} textAnchor="end" className="figure-label">
                {quarter.label}
              </text>
              <line
                x1={x(quarter.endDate)}
                x2={x(filed)}
                y1={y}
                y2={y}
                stroke={colour}
                strokeWidth={3}
                strokeLinecap="round"
                strokeDasharray={quarter.knowledge === "not_yet" ? "3 4" : undefined}
              />
              <rect
                x={x(quarter.endDate) - 4}
                y={y - 4}
                width={8}
                height={8}
                rx={1}
                fill="var(--color-canvas)"
                stroke={colour}
                strokeWidth={2}
              />
              {quarter.filedAt ? (
                <circle
                  cx={x(quarter.filedAt)}
                  cy={y}
                  r={5}
                  fill={colour}
                  stroke="var(--color-canvas)"
                  strokeWidth={2}
                >
                  <title>{`${quarter.label}: period ended ${quarter.endDate}, ${quarter.form ?? "filing"} filed ${quarter.filedAt}`}</title>
                </circle>
              ) : null}
            </g>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap gap-x-6 gap-y-2 text-small text-ink-muted">
        {(Object.keys(KNOWLEDGE_LABELS) as Knowledge[]).map((state) => (
          <span key={state} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block h-1 w-6 rounded-full"
              style={{ background: COLOURS[state] }}
            />
            {KNOWLEDGE_LABELS[state]}
          </span>
        ))}
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="inline-block size-2 border-2 border-ink-muted" />
          End of the quarter
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-full bg-ink-muted" />
          Filing published
        </span>
      </figcaption>
    </figure>
  );
}
