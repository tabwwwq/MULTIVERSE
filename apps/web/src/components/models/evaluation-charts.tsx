import { COVERAGE, ERRORS, NOMINAL } from "@/models/evaluation";

const LOW = -80;
const HIGH = 20;

function at(value: number): number {
  return ((value - LOW) / (HIGH - LOW)) * 100;
}

/** Each target and horizon: the change of error against persistence, with its 95% interval. */
export function ErrorChart() {
  const targets = [...new Set(ERRORS.map((row) => row.target))];
  return (
    <figure className="flex flex-col gap-4 rounded-panel border border-line bg-surface p-5">
      <figcaption className="flex flex-col gap-1">
        <span className="font-medium text-ink">
          Error against persistence, test years 2020 to 2026
        </span>
        <span className="text-small text-ink-muted">
          Change of the mean absolute error, in percent: left of zero the model beats repeating the
          last value. Lines are 95% bootstrap intervals over firms.
        </span>
      </figcaption>
      <div className="flex flex-col gap-4">
        {targets.map((target) => (
          <div key={target} className="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)] gap-3">
            <span className="pt-0.5 text-small text-ink">{target}</span>
            <ul className="flex flex-col gap-1.5">
              {ERRORS.filter((row) => row.target === target).map((row) => {
                const clear = row.high < 0;
                return (
                  <li
                    key={row.horizon}
                    className="grid grid-cols-[3.5rem_minmax(0,1fr)_5rem] items-center gap-2"
                  >
                    <span className="text-micro text-ink-muted">{row.horizon} q</span>
                    <span aria-hidden="true" className="relative h-4">
                      <span
                        className="absolute top-0 h-full w-px bg-ink-muted"
                        style={{ left: `${at(0)}%` }}
                      />
                      <span
                        className={`absolute top-1/2 h-1 -translate-y-1/2 rounded-pill ${clear ? "bg-mint/50" : "bg-warning/50"}`}
                        style={{ left: `${at(row.low)}%`, width: `${at(row.high) - at(row.low)}%` }}
                      />
                      <span
                        className={`absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ${clear ? "bg-mint" : "bg-warning"}`}
                        style={{ left: `${at(row.change)}%` }}
                      />
                    </span>
                    <span className="text-right text-micro text-ink tabular-nums">
                      {row.change.toFixed(1)}%
                      <span className="sr-only">
                        {" "}
                        ({row.low.toFixed(1)} to {row.high.toFixed(1)}
                        {clear ? ")" : ", the interval includes zero)"}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      <div aria-hidden="true" className="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)] gap-3">
        <span />
        <div className="grid grid-cols-[3.5rem_minmax(0,1fr)_5rem] gap-2">
          <span />
          <div className="relative h-4 text-micro text-ink-muted">
            {[-80, -40, 0].map((tick) => (
              <span
                key={tick}
                className="absolute -translate-x-1/2"
                style={{ left: `${at(tick)}%` }}
              >
                {tick}%
              </span>
            ))}
          </div>
        </div>
      </div>
      <p className="flex flex-wrap gap-x-5 gap-y-1 text-micro text-ink-muted">
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-full bg-mint" />
          Interval entirely below zero
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-full bg-warning" />
          Interval includes zero
        </span>
      </p>
    </figure>
  );
}

/** Share of outcomes inside the p10 to p90 band, against the 80% the band states. */
export function CoverageChart() {
  const at80 = (NOMINAL - 60) / 40;
  return (
    <figure className="flex flex-col gap-4 rounded-panel border border-line bg-surface p-5">
      <figcaption className="flex flex-col gap-1">
        <span className="font-medium text-ink">How often p10 to p90 held, 2024 to 2026</span>
        <span className="text-small text-ink-muted">
          Firms never used for training. The band states 80%; above it the band is wider than it
          needs to be. Approved pairs passed the rule written before scoring.
        </span>
      </figcaption>
      <ul className="flex flex-col gap-3">
        {COVERAGE.map((row) => (
          <li key={row.label} className="flex flex-col gap-1">
            <span className="flex items-baseline justify-between gap-2 text-small">
              <span className="text-ink">
                {row.label}
                {row.approved ? <span className="ml-2 text-micro text-mint">approved</span> : null}
              </span>
              <span className="text-ink tabular-nums">{row.held.toFixed(1)}%</span>
            </span>
            <span aria-hidden="true" className="relative h-2 rounded-pill bg-inset">
              <span
                className={`absolute inset-y-0 left-0 rounded-pill ${row.approved ? "bg-mint" : "bg-blue"}`}
                style={{ width: `${((row.held - 60) / 40) * 100}%` }}
              />
              <span
                className="absolute -inset-y-1 w-0.5 bg-ink"
                style={{ left: `${at80 * 100}%` }}
              />
            </span>
            <span className="text-micro text-ink-muted tabular-nums">
              {row.rows.toLocaleString("en-US")} outcomes
            </span>
          </li>
        ))}
      </ul>
      <p className="text-micro text-ink-muted">
        Bars start at 60%. The black mark is the stated 80%.
      </p>
    </figure>
  );
}
