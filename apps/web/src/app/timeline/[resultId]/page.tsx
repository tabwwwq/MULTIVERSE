import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { RawParams } from "@/companies/params";
import { EventTimeline } from "@/components/results/result-figures";
import { ResultHeader, ResultNotClaims } from "@/components/results/result-header";
import { TimelineExplorer } from "@/components/results/timeline-explorer";
import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { Section } from "@/layouts/page-header";
import { parseResultParams } from "@/results/params";
import { getResultRepository } from "@/results/repository";

interface PageProps {
  params: Promise<{ resultId: string }>;
  searchParams: Promise<RawParams>;
}

// Only known result IDs render; anything else is a 404 (safe URL behaviour).
export const dynamicParams = false;

export async function generateStaticParams() {
  const ids = await getResultRepository().listIds();
  return ids.map((resultId) => ({ resultId }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const result = await getResultRepository().get((await params).resultId);
  return { title: result ? `${result.title} · Timeline` : "Timeline Explorer" };
}

export default async function TimelinePage({ params, searchParams }: PageProps) {
  const repository = getResultRepository();
  const result = await repository.get((await params).resultId);
  if (!result) notFound();
  const { metric, mode, ignored } = parseResultParams(
    await searchParams,
    await repository.listIds(),
  );

  return (
    <>
      <ResultHeader
        result={result}
        summary={`${result.company_name}, knowledge cutoff ${result.as_of}, ${result.horizon_quarters} quarters ahead.`}
      />
      {ignored.length > 0 ? (
        <div className="mb-6 max-w-3xl">
          <Alert tone="info" title="Some settings in the link were ignored">
            Unsupported values for: {ignored.join(", ")}.
          </Alert>
        </div>
      ) : null}
      {result.status === "completed" ? (
        <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="flex min-w-0 flex-col gap-10">
            <TimelineExplorer result={result} initialMetric={metric} initialMode={mode} />
            <Section
              id="events"
              title="Event timeline"
              intro="Dates of the decisions and their effects, from the decision inputs."
            >
              <EventTimeline events={result.events} />
            </Section>
          </div>
          <aside className="flex flex-col gap-4">
            <ResultNotClaims />
            <ButtonLink href={`/compare/${result.result_id}`} variant="secondary">
              Compare these scenarios
            </ButtonLink>
            <p className="text-small text-ink-muted">
              Seed {result.seed}, {result.paths} paths. The same seed gives the same numbers.{" "}
              <Link href="/timeline" className="text-mint underline underline-offset-4">
                All results
              </Link>
            </p>
          </aside>
        </div>
      ) : (
        <ButtonLink href="/timeline" variant="secondary">
          Choose another result
        </ButtonLink>
      )}
    </>
  );
}
