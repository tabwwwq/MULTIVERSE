import type { DocLink } from "@multiverse/contracts";
import type { DataSource } from "@multiverse/contracts/sources";
import { ExternalLink, PowerOff } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { safeExternalUrl } from "@/lib/safe-url";
import {
  ACCESS_LABELS,
  DECISION_LABELS,
  DOC_KIND_LABELS,
  KEY_LABELS,
  RESALE_LABELS,
} from "@/sources/catalog";

const ACCESS_TONES: Record<DataSource["access"], BadgeTone> = {
  public_access: "mint",
  api_key: "blue",
  licensed: "violet",
};

export function AccessBadge({ access }: { access: DataSource["access"] }) {
  return <Badge tone={ACCESS_TONES[access]}>{ACCESS_LABELS[access]}</Badge>;
}

/** Downloads stay off until the owner decides; the badge says so on every source. */
export function DownloadBadge({ source }: { source: DataSource }) {
  const off = source.download.status !== "approved";
  return (
    <Badge tone={off ? "warning" : "mint"} {...(off ? { icon: PowerOff } : {})}>
      {DECISION_LABELS[source.download.status]}
    </Badge>
  );
}

export interface Fact {
  term: string;
  detail: ReactNode;
}

export function Facts({ items, compact = false }: { items: readonly Fact[]; compact?: boolean }) {
  return (
    <dl
      className={cn(
        "grid max-w-4xl gap-x-6 gap-y-3",
        compact
          ? "grid-cols-[auto_minmax(0,1fr)]"
          : "sm:grid-cols-[minmax(9rem,13rem)_minmax(0,1fr)]",
      )}
    >
      {items.map((item) => (
        <div key={item.term} className="contents">
          <dt className="text-small font-medium text-ink">{item.term}</dt>
          <dd className="text-small text-ink-muted [overflow-wrap:anywhere]">{item.detail}</dd>
        </div>
      ))}
    </dl>
  );
}

export function TextList({ items }: { items: readonly string[] }) {
  return (
    <ul className="flex list-disc flex-col gap-1 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

/** Links to official documentation only; anything else is shown as plain text. */
export function DocLinks({ docs }: { docs: readonly DocLink[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {docs.map((doc) => {
        const href = safeExternalUrl(doc.url);
        return (
          <li key={doc.url} className="flex flex-col gap-0.5 text-small sm:flex-row sm:gap-3">
            <span className="shrink-0 text-ink-muted sm:w-32">{DOC_KIND_LABELS[doc.kind]}</span>
            {href ? (
              <a
                href={href}
                rel="noopener noreferrer"
                className="inline-flex items-start gap-1 text-blue underline [overflow-wrap:anywhere]"
              >
                {doc.title}
                <ExternalLink aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                <span className="sr-only"> (official site)</span>
              </a>
            ) : (
              <span>{doc.title}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function SourceCard({ source, matches }: { source: DataSource; matches: string[] }) {
  return (
    <article className="flex h-full flex-col gap-3 rounded-panel border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-display text-h4 font-semibold text-ink">
          <Link
            href={`/data-catalog/${source.source_id}`}
            className="rounded-control underline-offset-4 hover:underline"
          >
            {source.name}
          </Link>
        </h3>
        <AccessBadge access={source.access} />
      </div>
      <p className="text-small text-ink-muted">
        {source.publisher} · {source.region}
      </p>
      <Facts
        compact
        items={[
          { term: "Key", detail: KEY_LABELS[source.key_status] },
          { term: "Resale", detail: RESALE_LABELS[source.licence.resale] },
          { term: "Datasets", detail: source.datasets.length },
          { term: "Checked on", detail: source.verified_on },
        ]}
      />
      <div className="mt-auto flex flex-col gap-2">
        <DownloadBadge source={source} />
        {matches.length > 0 ? (
          <p className="text-micro text-ink-muted">Matched in: {matches.join("; ")}</p>
        ) : null}
      </div>
    </article>
  );
}
