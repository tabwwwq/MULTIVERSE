import type { DossierView, QuarterRow } from "@/companies/pit";

/*
 * The company in four numbers before the tables: the last four quarters public at the cutoff,
 * summed, with revenue by quarter drawn small. Calculated from the same cells the table shows.
 */

function amount(row: QuarterRow, metric: string): number | null {
  const cell = row.cells[metric];
  return cell?.state === "value" && cell.value.quantity ? Number(cell.value.quantity.value) : null;
}

function sum(rows: readonly QuarterRow[], metric: string): number | null {
  const values = rows.map((row) => amount(row, metric));
  return values.every((value) => value !== null)
    ? values.reduce<number>((total, value) => total + (value ?? 0), 0)
    : null;
}

function money(value: number | null, currency: string): string {
  if (value === null) return "Not public";
  const size = Math.abs(value);
  const text = size >= 1e9 ? `${(size / 1e9).toFixed(1)}bn` : `${(size / 1e6).toFixed(0)}m`;
  return `${value < 0 ? "−" : ""}${currency} ${text}`;
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const low = Math.min(...values, 0);
  const high = Math.max(...values);
  const x = (index: number) => (index / (values.length - 1)) * 100;
  const y = (value: number) => 28 - ((value - low) / (high - low || 1)) * 26;
  const line = values.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  return (
    <svg
      viewBox="0 0 100 30"
      preserveAspectRatio="none"
      aria-hidden="true"
      className="mt-2 h-8 w-full"
    >
      <polyline
        points={`0,30 ${line} 100,30`}
        fill="var(--color-mint)"
        fillOpacity={0.12}
        stroke="none"
      />
      <polyline
        points={line}
        fill="none"
        stroke="var(--color-mint)"
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function KeyFigures({ view, currency }: { view: DossierView; currency: string }) {
  const public4 = view.rows.filter((row) => amount(row, "revenue") !== null);
  const last = public4.slice(0, 4);
  const before = public4.slice(4, 8);
  if (last.length < 4) return null;
  const revenue = sum(last, "revenue");
  const earlier = before.length === 4 ? sum(before, "revenue") : null;
  const ebitda = sum(last, "ebitda_calculated");
  const fcf = sum(last, "fcf_simple");
  const netDebt =
    view.rows.map((row) => amount(row, "net_debt")).find((value) => value !== null) ?? null;
  const growth = revenue !== null && earlier ? revenue / earlier - 1 : null;
  const margin = revenue && ebitda !== null ? ebitda / revenue : null;
  const history = [...public4].reverse().map((row) => amount(row, "revenue") ?? 0);
  const span = `${last[3]?.label} to ${last[0]?.label}`;

  const figures = [
    {
      label: "Revenue, last four quarters",
      value: money(revenue, currency),
      note:
        growth === null
          ? span
          : `${growth >= 0 ? "+" : "−"}${Math.abs(growth * 100).toFixed(1)}% on the four before`,
      chart: <Sparkline values={history} />,
    },
    {
      label: "EBITDA margin (calculated)",
      value: margin === null ? "Not public" : `${(margin * 100).toFixed(1)}%`,
      note: money(ebitda, currency),
    },
    { label: "FCF (CFO − CAPEX)", value: money(fcf, currency), note: span },
    {
      label: "Net debt, latest quarter",
      value: money(netDebt, currency),
      note:
        netDebt === null ? "Not public" : netDebt < 0 ? "More cash than debt" : "Debt minus cash",
    },
  ];

  return (
    <section aria-labelledby="key-figures" className="mb-12">
      <h2 id="key-figures" className="sr-only">
        Key figures, as known on {view.cutoff}
      </h2>
      <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {figures.map((figure) => (
          <div
            key={figure.label}
            className="flex flex-col rounded-panel border border-line bg-surface p-4"
          >
            <dt className="text-small text-ink-muted">{figure.label}</dt>
            <dd className="mt-1 font-display text-h3 text-ink tabular-nums">{figure.value}</dd>
            <dd className="text-micro text-ink-muted">{figure.note}</dd>
            {figure.chart ? <dd>{figure.chart}</dd> : null}
          </div>
        ))}
      </dl>
      <p className="mt-2 text-micro text-ink-muted">
        Sums of the quarters public on {view.cutoff}, from the table of financial history below.
      </p>
    </section>
  );
}
