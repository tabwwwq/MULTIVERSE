import { Info } from "lucide-react";

interface NotClaimsProps {
  items: readonly string[];
  title?: string;
}

/** "What this does not mean", shown next to every result (PRD FR-RE-05, REP-02). */
export function NotClaims({ items, title = "What this does not mean" }: NotClaimsProps) {
  return (
    <aside aria-label={title} className="rounded-panel border border-line bg-inset p-4">
      <p className="flex items-center gap-2 font-medium text-ink">
        <Info aria-hidden="true" className="size-4 text-blue" />
        {title}
      </p>
      <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-small text-ink-muted">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </aside>
  );
}
