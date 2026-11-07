import type { SimulationReport } from "@multiverse/contracts";
import { formatValue } from "@/results/format";

type Value = SimulationReport["values"][number];
type Risk = SimulationReport["risks"][number];

const RISK_LABELS: Record<Risk["risk"], string> = {
  funding_shortfall: "Funding shortfall",
  covenant_breach: "Covenant breach",
  below_minimum_cash: "Cash below its minimum",
  negative_fcff_year: "A year of negative FCFF",
};

function usd(value: string | null | undefined, signed = false): string {
  return value === null || value === undefined
    ? "undefined"
    : formatValue(Number(value), "usd", { signed });
}

function find(report: SimulationReport, metric: Value["metric"], scenario: Value["scenario"]) {
  return report.values.find((row) => row.metric === metric && row.scenario === scenario);
}

/** Where p10, p50 and p90 of the paired change sit against zero. */
function ChangeBar({ change }: { change: Value }) {
  const low = Number(change.p10 ?? 0);
  const middle = Number(change.p50 ?? 0);
  const high = Number(change.p90 ?? 0);
  const reach = Math.max(Math.abs(low), Math.abs(high), 1);
  const at = (value: number) => 50 + (45 * value) / reach;
  const tone = middle < 0 ? "bg-negative" : "bg-mint";
  return (
    <div aria-hidden="true" className="relative mt-4 h-8">
      <div className="absolute top-1/2 h-px w-full -translate-y-1/2 bg-line" />
      <div className="absolute top-0 h-full w-px bg-ink-muted" style={{ left: "50%" }} />
      <div
        className={`absolute top-1/2 h-2 -translate-y-1/2 rounded-pill ${tone} opacity-40`}
        style={{ left: `${at(low)}%`, width: `${at(high) - at(low)}%` }}
      />
      <div
        className={`absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-canvas ${tone}`}
        style={{ left: `${at(middle)}%` }}
      />
      <span className="absolute -bottom-4 left-1/2 -translate-x-1/2 text-micro text-ink-muted">
        0
      </span>
    </div>
  );
}

/** The answer of a run before its charts: the change of value and of each risk, under the model. */
export function RunSummary({ report }: { report: SimulationReport }) {
  const change = find(report, "ev_change", "alt_a");
  const before = find(report, "enterprise_value", "baseline");
  const after = find(report, "enterprise_value", "alt_a");
  const risks = (Object.keys(RISK_LABELS) as Risk["risk"][]).map((risk) => ({
    risk,
    baseline: report.risks.find((row) => row.risk === risk && row.scenario === "baseline"),
    decision: report.risks.find((row) => row.risk === risk && row.scenario === "alt_a"),
  }));

  return (
    <section
      aria-labelledby="run-answer"
      className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
    >
      <h2 id="run-answer" className="sr-only">
        The answer of this run
      </h2>
      <div className="flex flex-col rounded-panel border border-line bg-surface p-5">
        <p className="text-small text-ink-muted">
          Paired change of model enterprise value, median path
        </p>
        <p className="mt-1 font-display text-h2 text-ink tabular-nums">{usd(change?.p50, true)}</p>
        <p className="text-small text-ink-muted tabular-nums">
          p10 {usd(change?.p10, true)} to p90 {usd(change?.p90, true)}
        </p>
        {change ? <ChangeBar change={change} /> : null}
        <dl className="mt-8 grid grid-cols-2 gap-4 border-t border-line pt-4">
          <div>
            <dt className="text-micro text-ink-muted">Without the decision, p50</dt>
            <dd className="text-body text-ink tabular-nums">{usd(before?.p50)}</dd>
          </div>
          <div>
            <dt className="text-micro text-ink-muted">With the decision, p50</dt>
            <dd className="text-body text-ink tabular-nums">{usd(after?.p50)}</dd>
          </div>
        </dl>
      </div>

      <div className="rounded-panel border border-line bg-surface p-5">
        <p className="text-small text-ink-muted">
          Share of paths with each event within the horizon
        </p>
        <ul className="mt-4 flex flex-col gap-4">
          {risks.map(({ risk, baseline, decision }) => (
            <li
              key={risk}
              className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] items-center gap-3"
            >
              <span className="text-small text-ink">{RISK_LABELS[risk]}</span>
              <div className="flex flex-col gap-1.5">
                {[
                  { label: "Baseline", row: baseline, tone: "bg-series-baseline" },
                  { label: "With the decision", row: decision, tone: "bg-series-alt-a" },
                ].map(({ label, row, tone }) => {
                  const share = row?.probability ?? 0;
                  return (
                    <div key={label} className="flex items-center gap-2">
                      <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-pill bg-inset">
                        <div
                          className={`h-full rounded-pill ${tone}`}
                          style={{ width: `${Math.max(share * 100, share > 0 ? 1 : 0)}%` }}
                        />
                      </div>
                      <span className="w-40 text-right text-micro text-ink-muted tabular-nums">
                        {label}: {share === 0 ? "none seen" : `${(share * 100).toFixed(1)}%`}
                      </span>
                    </div>
                  );
                })}
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-micro text-ink-muted">
          Shares of simulated paths under the assumed model, not probabilities of the real world.
          The risk table below gives each with its Monte Carlo error.
        </p>
      </div>
    </section>
  );
}
