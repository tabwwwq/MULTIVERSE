import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "warning" | "negative";

const TONES = {
  info: { icon: Info, frame: "border-blue/50", iconColor: "text-blue" },
  success: { icon: CircleCheck, frame: "border-mint/50", iconColor: "text-mint" },
  warning: { icon: TriangleAlert, frame: "border-warning/50", iconColor: "text-warning" },
  negative: { icon: CircleAlert, frame: "border-negative/50", iconColor: "text-negative" },
} as const;

interface AlertProps {
  tone?: Tone;
  title: string;
  children?: ReactNode;
  /** Announce the alert to screen readers when it appears after page load. */
  live?: boolean;
  className?: string;
}

export function Alert({ tone = "info", title, children, live = false, className }: AlertProps) {
  const { icon: Icon, frame, iconColor } = TONES[tone];
  return (
    <div
      role={live ? "status" : undefined}
      className={cn("flex gap-3 rounded-panel border border-l-4 bg-surface p-4", frame, className)}
    >
      <Icon aria-hidden="true" className={cn("mt-0.5 size-5 shrink-0", iconColor)} />
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-medium text-ink">{title}</p>
        {children ? <div className="text-small text-ink-muted">{children}</div> : null}
      </div>
    </div>
  );
}
