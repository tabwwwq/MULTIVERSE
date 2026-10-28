import type { ResultMode, UncertaintyType } from "@multiverse/contracts";
import { InferenceModeBadge } from "@/components/trust/inference-mode-badge";

export const UNCERTAINTY_LABELS: Record<UncertaintyType, string> = {
  none: "No uncertainty band",
  predictive_quantiles: "Predictive quantiles",
  conditional_model_quantiles: "Conditional model quantiles",
  calibrated_interval: "Calibrated interval",
};

export interface TrustHeaderProps {
  mode: ResultMode;
  evidence: string;
  /** Knowledge cutoff, ISO date. */
  asOf: string;
  model: string;
  uncertainty: UncertaintyType;
  calibrated: boolean;
  auditId: string;
}

/** The six facts every result header shows (docs/10, Trust UX). */
export function TrustHeader({
  mode,
  evidence,
  asOf,
  model,
  uncertainty,
  calibrated,
  auditId,
}: TrustHeaderProps) {
  const items = [
    { term: "Mode", detail: <InferenceModeBadge mode={mode} /> },
    { term: "Evidence", detail: evidence },
    { term: "As of", detail: <time dateTime={asOf}>{asOf}</time> },
    { term: "Model", detail: model },
    {
      term: "Uncertainty",
      detail: `${UNCERTAINTY_LABELS[uncertainty]}, ${calibrated ? "calibrated" : "not calibrated"}`,
    },
    { term: "Audit ID", detail: <span className="tabular-nums">{auditId}</span> },
  ];
  return (
    <dl className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-px overflow-hidden rounded-panel border border-line bg-line">
      {items.map(({ term, detail }) => (
        <div key={term} className="flex flex-col gap-1 bg-surface px-4 py-3">
          <dt className="text-micro text-ink-muted">{term}</dt>
          <dd className="text-small text-ink">{detail}</dd>
        </div>
      ))}
    </dl>
  );
}
