import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "mint" | "blue" | "violet" | "warning" | "negative";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-line-strong text-ink-muted",
  mint: "border-mint/60 text-mint",
  blue: "border-blue/60 text-blue",
  violet: "border-violet/60 text-violet",
  warning: "border-warning/60 text-warning",
  negative: "border-negative/60 text-negative",
};

interface BadgeProps {
  tone?: BadgeTone;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
}

/** A short status label. The text carries the meaning; the colour only supports it. */
export function Badge({ tone = "neutral", icon: Icon, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border bg-canvas/40 px-2.5 py-0.5 text-micro font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {Icon ? <Icon aria-hidden="true" className="size-3.5 shrink-0" /> : null}
      {children}
    </span>
  );
}
