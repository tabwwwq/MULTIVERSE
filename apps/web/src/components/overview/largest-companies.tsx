import type { RealCompanyRow } from "@multiverse/contracts";
import Link from "next/link";
import { SECTOR_LABELS } from "@/companies/labels";

function trillions(value: number): string {
  return value >= 1e12 ? `$${(value / 1e12).toFixed(2)}tn` : `$${(value / 1e9).toFixed(0)}bn`;
}

/** The largest SEC filers by public float, one bar each, longest first. */
export function LargestCompanies({ rows }: { rows: readonly RealCompanyRow[] }) {
  const largest = rows[0]?.evidence.public_float_usd ?? 1;
  return (
    <figure
      data-testid="largest-companies"
      className="flex flex-col gap-4 rounded-frame border border-line bg-surface p-5 md:p-6"
    >
      <figcaption className="flex flex-col gap-1">
        <span className="font-display text-h4 text-ink">The largest companies on file</span>
        <span className="text-small text-ink-muted">
          Public float from the cover of each 10-K, not market capitalization.
        </span>
      </figcaption>
      <ol className="flex flex-col gap-2.5">
        {rows.map((row, index) => {
          const share = row.evidence.public_float_usd / largest;
          return (
            <li key={row.company_id}>
              <Link
                href={`/dossier/${row.company_id}`}
                className="group grid grid-cols-[1.75rem_minmax(0,9rem)_minmax(0,1fr)_4.5rem] items-center gap-3 rounded-control py-0.5 focus-visible:outline-offset-4 sm:grid-cols-[1.75rem_minmax(0,12rem)_minmax(0,1fr)_4.5rem]"
              >
                <span className="text-right text-micro text-ink-muted tabular-nums">
                  {row.evidence.rank}
                </span>
                <span className="truncate text-small text-ink group-hover:text-mint">
                  {row.name}
                  <span className="sr-only">
                    , {SECTOR_LABELS[row.sector]}, public float{" "}
                    {trillions(row.evidence.public_float_usd)}
                  </span>
                </span>
                <span aria-hidden="true" className="h-2.5 overflow-hidden rounded-pill bg-inset">
                  <span
                    className="float-bar block h-full rounded-pill bg-mint/80 group-hover:bg-mint"
                    style={{
                      width: `${Math.max(share * 100, 2)}%`,
                      animationDelay: `${index * 45}ms`,
                    }}
                  />
                </span>
                <span aria-hidden="true" className="text-right text-small text-ink tabular-nums">
                  {trillions(row.evidence.public_float_usd)}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
      <Link
        href="/universe"
        className="self-start text-small text-mint underline underline-offset-4"
      >
        All {rows.length < 500 ? "500" : rows.length} companies in the Universe Explorer
      </Link>
    </figure>
  );
}
