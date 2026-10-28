import type { ResultMode } from "@multiverse/contracts";
import { Compass, FlaskConical, LineChart, Network } from "lucide-react";
import { Badge, type BadgeTone } from "@/components/ui/badge";

export const RESULT_MODE_LABELS: Record<
  ResultMode,
  { label: string; tone: BadgeTone; icon: typeof FlaskConical }
> = {
  demo: { label: "Demo data", tone: "warning", icon: FlaskConical },
  empirical_forecast: { label: "Empirical forecast", tone: "blue", icon: LineChart },
  causal_study: { label: "Causal study", tone: "violet", icon: Network },
  fictional_exploratory: { label: "Fictional scenario", tone: "neutral", icon: Compass },
};

/** Mode of a result (PRD §6). The mode is chosen by the system, never by the user. */
export function InferenceModeBadge({ mode }: { mode: ResultMode }) {
  const { label, tone, icon } = RESULT_MODE_LABELS[mode];
  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  );
}
