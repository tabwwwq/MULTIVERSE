import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import type { ResultSummary } from "@/results/repository";

/** Results to open, with their status; used by the Timeline Explorer and Universe Compare. */
export function ResultList({
  results,
  basePath,
}: {
  results: readonly ResultSummary[];
  basePath: string;
}) {
  if (results.length === 0) {
    return (
      <p className="text-body text-ink-muted">
        No results yet. Results appear here after a run; until the Monte Carlo engine exists (Stage
        22) only mock results are listed.
      </p>
    );
  }
  return (
    <ul className="flex max-w-3xl flex-col divide-y divide-line rounded-panel border border-line bg-surface">
      {results.map((result) => (
        <li key={result.resultId} className="flex flex-col gap-1 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Link
              href={`${basePath}/${result.resultId}`}
              className="rounded-control font-medium text-ink hover:text-mint"
            >
              {result.title}
            </Link>
            {result.status === "failed" ? (
              <Badge tone="negative">Failed</Badge>
            ) : (
              <Badge tone="warning">Mock</Badge>
            )}
          </div>
          <p className="text-small text-ink-muted">
            {result.companyName} · cutoff {result.asOf} ·{" "}
            {result.scenarios.join(", ") || "no scenarios"}
          </p>
        </li>
      ))}
    </ul>
  );
}
