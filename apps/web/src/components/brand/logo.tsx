import Link from "next/link";
import { cn } from "@/lib/cn";

/** Brand mark: one history splitting into three paths inside an orbit. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("size-8 shrink-0", className)}>
      <ellipse
        cx="16"
        cy="16"
        rx="13"
        ry="6"
        transform="rotate(-20 16 16)"
        fill="none"
        stroke="var(--color-line-strong)"
        strokeWidth="1.5"
      />
      <path
        d="M3 21 L15 16"
        stroke="var(--color-observed)"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M15 16 L29 8"
        stroke="var(--color-mint)"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M15 16 L29 15"
        stroke="var(--color-blue)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray="2.5 2.5"
        fill="none"
      />
      <path
        d="M15 16 L29 22"
        stroke="var(--color-violet)"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
      <circle
        cx="15"
        cy="16"
        r="2.25"
        fill="var(--color-canvas)"
        stroke="var(--color-ink)"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function BrandLink({
  compact = false,
  onNavigate,
}: {
  compact?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href="/"
      {...(onNavigate ? { onClick: onNavigate } : {})}
      className="flex min-h-12 items-center gap-2.5 rounded-control px-1 text-ink"
    >
      <LogoMark />
      <span
        className={cn(
          "font-display text-h4 leading-none font-semibold tracking-tight",
          compact && "sr-only",
        )}
      >
        MULTIVERSE
      </span>
    </Link>
  );
}
