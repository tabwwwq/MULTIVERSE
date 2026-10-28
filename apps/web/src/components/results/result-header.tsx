import type { ScenarioResult } from "@multiverse/contracts";
import { FlaskConical, Shapes } from "lucide-react";
import Link from "next/link";
import { NotClaims } from "@/components/trust/not-claims";
import { TrustHeader } from "@/components/trust/trust-header";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/layouts/page-header";

export const RESULT_NOT_CLAIMS = [
  "These are mock paths from an interface generator, not a forecast of what the company would earn.",
  "The p10 to p90 bands are not calibrated: they are not confidence intervals and carry no coverage guarantee.",
  "A difference between scenarios is not a causal effect of the decision.",
  "EV here is ten times trailing EBITDA, an illustration rather than a valuation or a share price.",
];

/** Title, mode badges and the trust header every result screen shows (PRD FR-RE-04). */
export function ResultHeader({ result, summary }: { result: ScenarioResult; summary: string }) {
  const quarters = result.metrics[0]?.observed.length ?? 0;
  return (
    <>
      <PageHeader
        title={result.title}
        summary={summary}
        meta={
          <>
            <Badge tone="warning" icon={FlaskConical}>
              Synthetic
            </Badge>
            <Badge tone="warning" icon={Shapes}>
              Mock result
            </Badge>
          </>
        }
      />
      <div className="mb-8 flex flex-col gap-4">
        <TrustHeader
          mode={result.mode}
          evidence={
            result.status === "completed"
              ? `${quarters} quarters of synthetic history, ${result.manifest.source_ids.length} synthetic filings`
              : "No numbers: the run failed"
          }
          asOf={result.as_of}
          model={result.model}
          uncertainty={result.uncertainty_type}
          calibrated={result.calibrated}
          auditId={result.result_id.slice(0, 8)}
        />
        {result.status === "failed" && result.failure ? (
          <Alert tone="negative" title="This run failed">
            {result.failure.message} Incident ID:{" "}
            <span className="tabular-nums">{result.failure.incident_id}</span>. A retry with the
            same settings is safe: it creates no second result. Runs arrive with the Monte Carlo
            engine (Stage 22).{" "}
            <Link href="/timeline" className="text-mint underline underline-offset-4">
              Back to all results
            </Link>
          </Alert>
        ) : null}
      </div>
    </>
  );
}

export function ResultNotClaims() {
  return <NotClaims items={RESULT_NOT_CLAIMS} />;
}
