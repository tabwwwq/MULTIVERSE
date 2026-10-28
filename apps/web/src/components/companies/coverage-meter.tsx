import { cn } from "@/lib/cn";

interface CoverageMeterProps {
  label: string;
  valid: number;
  expected: number;
  className?: string;
}

/** Share of fiscal quarters with a valid value. The text carries the numbers; the bar only shows them. */
export function CoverageMeter({ label, valid, expected, className }: CoverageMeterProps) {
  const share = expected > 0 ? valid / expected : 0;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline justify-between gap-3 text-small">
        <span className="text-ink-muted">{label}</span>
        <span className="text-ink tabular-nums">
          {expected > 0 ? `${valid} of ${expected} quarters` : "No quarterly data"}
        </span>
      </div>
      <div aria-hidden="true" className="h-1.5 overflow-hidden rounded-pill bg-inset">
        <div
          className={cn("h-full rounded-pill", share >= 1 ? "bg-mint" : share > 0 ? "bg-blue" : "")}
          style={{ width: `${Math.round(share * 100)}%` }}
        />
      </div>
    </div>
  );
}
