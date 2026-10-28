import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader, Section } from "@/layouts/page-header";
import { SECTIONS, formatStage, groupLabel } from "@/navigation/sections";

/*
 * Placeholder for sections that are planned but not built. It names the stage that
 * builds them and shows no numbers or controls, so it never imitates readiness.
 */

const PLANNED = SECTIONS.filter((section) => section.status === "planned");

export const dynamicParams = false;

export function generateStaticParams() {
  return PLANNED.map((section) => ({ section: section.slug }));
}

interface PageProps {
  params: Promise<{ section: string }>;
}

function findPlanned(slug: string) {
  return PLANNED.find((section) => section.slug === slug);
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const section = findPlanned((await params).section);
  return section ? { title: `${section.title} (planned)` } : {};
}

export default async function PlannedSectionPage({ params }: PageProps) {
  const section = findPlanned((await params).section);
  if (!section) notFound();

  return (
    <>
      <PageHeader
        title={section.title}
        summary={section.summary}
        meta={
          <>
            <Badge>{groupLabel(section.group)}</Badge>
            <Badge tone="blue">Planned for {formatStage(section.stage)}</Badge>
          </>
        }
      />
      <div className="max-w-prose">
        <Alert tone="info" title="Not built yet">
          This section arrives in {formatStage(section.stage)}: {section.stageName}. Nothing here
          shows data or accepts input until then.
        </Alert>
      </div>
      <Section id="plans" title="What this section will do">
        <ul className="flex max-w-prose list-disc flex-col gap-2 pl-5 text-body text-ink-muted">
          {section.plans.map((plan) => (
            <li key={plan}>{plan}</li>
          ))}
        </ul>
        <div className="mt-8 flex flex-wrap gap-3">
          <ButtonLink href="/methodology" variant="secondary">
            Read the methodology
          </ButtonLink>
          <ButtonLink href="/" variant="ghost">
            Back to the overview
          </ButtonLink>
        </div>
      </Section>
    </>
  );
}
