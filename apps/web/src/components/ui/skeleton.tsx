import { cn } from "@/lib/cn";

/** A placeholder block. Always place it inside a container that announces what is loading. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("skeleton rounded-control bg-inset", className)} />;
}

interface LoadingRegionProps {
  /** What is loading, read by screen readers, e.g. "Loading company data". */
  label: string;
  className?: string;
  children: React.ReactNode;
}

export function LoadingRegion({ label, className, children }: LoadingRegionProps) {
  return (
    <div aria-busy="true" className={className}>
      <span role="status" className="sr-only">
        {label}
      </span>
      {children}
    </div>
  );
}
