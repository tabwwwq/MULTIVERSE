import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  summary?: ReactNode;
  meta?: ReactNode;
}

export function PageHeader({ title, summary, meta }: PageHeaderProps) {
  return (
    <header className="mb-10 flex max-w-prose flex-col gap-3">
      {meta ? <div className="flex flex-wrap gap-2">{meta}</div> : null}
      <h1 className="font-display text-h2 font-semibold tracking-tight text-ink md:text-h1">
        {title}
      </h1>
      {summary ? <p className="text-lead text-ink-muted">{summary}</p> : null}
    </header>
  );
}

interface SectionProps {
  id: string;
  title: string;
  intro?: ReactNode;
  children: ReactNode;
}

/** A titled page section. Separation comes from the heading and spacing, not a card. */
export function Section({ id, title, intro, children }: SectionProps) {
  return (
    <section aria-labelledby={`${id}-title`} className="mt-16 first:mt-0">
      <h2 id={`${id}-title`} className="font-display text-h3 font-semibold tracking-tight text-ink">
        {title}
      </h2>
      {intro ? <div className="mt-2 max-w-prose text-body text-ink-muted">{intro}</div> : null}
      <div className="mt-6">{children}</div>
    </section>
  );
}
