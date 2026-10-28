import type { DataOrigin, ValueKind } from "@multiverse/contracts";
import { Database, FlaskConical, LineChart, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const KIND = {
  observed: { label: "Observed", icon: Database, tone: "neutral" },
  forecast: { label: "Forecast", icon: LineChart, tone: "blue" },
  simulated: { label: "Simulated", icon: Sparkles, tone: "mint" },
} as const satisfies Record<ValueKind, unknown>;

interface SourceBadgeProps {
  kind: ValueKind;
  origin: DataOrigin;
}

/** Where a number comes from in time, and whether it is real or synthetic (PRD SYN-04). */
export function SourceBadge({ kind, origin }: SourceBadgeProps) {
  const { label, icon, tone } = KIND[kind];
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Badge tone={tone} icon={icon}>
        {label}
      </Badge>
      {origin === "synthetic" ? (
        <Badge tone="warning" icon={FlaskConical}>
          Synthetic
        </Badge>
      ) : null}
    </span>
  );
}
