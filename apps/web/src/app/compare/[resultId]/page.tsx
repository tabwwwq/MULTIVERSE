import type { Metadata } from "next";
import Form from "next/form";
import { notFound } from "next/navigation";
import type { RawParams } from "@/companies/params";
import { CompareTable } from "@/components/results/compare-table";
import { DistributionFigure, WaterfallFigure } from "@/components/results/result-figures";
import { ResultHeader, ResultNotClaims } from "@/components/results/result-header";
import { Alert } from "@/components/ui/alert";
import { Button, ButtonLink } from "@/components/ui/button";
import { SelectField } from "@/components/ui/field";
import { Section } from "@/layouts/page-header";
import { compatibility } from "@/results/compare";
import { parseResultParams } from "@/results/params";
import { getResultRepository } from "@/results/repository";

interface PageProps {
  params: Promise<{ resultId: string }>;
  searchParams: Promise<RawParams>;
}

export const dynamicParams = false;

export async function generateStaticParams() {
  const ids = await getResultRepository().listIds();
  return ids.map((resultId) => ({ resultId }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const result = await getResultRepository().get((await params).resultId);
  return { title: result ? `${result.title} · Compare` : "Universe Compare" };
}

export default async function ComparePage({ params, searchParams }: PageProps) {
  const repository = getResultRepository();
  const result = await repository.get((await params).resultId);
  if (!result) notFound();
  const all = await repository.list();
  const { compareWith, ignored } = parseResultParams(
    await searchParams,
    await repository.listIds(),
  );
  const other =
    compareWith && compareWith !== result.result_id ? await repository.get(compareWith) : null;
  const check = other ? compatibility(result, other) : null;

  return (
    <>
      <ResultHeader
        result={result}
        summary={`${result.company_name}, knowledge cutoff ${result.as_of}. Paired scenarios with one seed.`}
      />
      {ignored.length > 0 ? (
        <div className="mb-6 max-w-3xl">
          <Alert tone="info" title="Some settings in the link were ignored">
            Unsupported values for: {ignored.join(", ")}.
          </Alert>
        </div>
      ) : null}
      {result.status !== "completed" ? (
        <ButtonLink href="/compare" variant="secondary">
          Choose another result
        </ButtonLink>
      ) : (
        <div className="flex flex-col gap-10">
          <div className="flex min-w-0 flex-col">
            <Section
              id="kpis"
              title="Key figures side by side"
              intro="Medians with p10 to p90 at the horizon, and the paired difference against the baseline."
            >
              <CompareTable result={result} caption={result.title} />
            </Section>

            <Section id="waterfalls" title="From baseline to each alternate">
              <div className="grid gap-4 lg:grid-cols-2">
                {result.waterfalls.map((waterfall) => (
                  <WaterfallFigure key={waterfall.scenario} waterfall={waterfall} result={result} />
                ))}
              </div>
            </Section>

            <Section
              id="distributions"
              title="Distribution of paired differences"
              intro="How much an alternate differs from its own baseline path, across all mock paths, at the horizon."
            >
              <div className="grid gap-4 lg:grid-cols-2">
                {result.distributions.map((distribution) => (
                  <DistributionFigure
                    key={`${distribution.scenario}-${distribution.metric}`}
                    distribution={distribution}
                    result={result}
                  />
                ))}
              </div>
            </Section>

            <Section
              id="other"
              title="Compare with another result"
              intro="Allowed only for the same company, knowledge cutoff, currency and horizon (PRD FR-RE-06)."
            >
              <Form
                action={`/compare/${result.result_id}`}
                className="flex max-w-2xl flex-wrap items-end gap-3"
              >
                <div className="min-w-0 flex-1">
                  <SelectField
                    id="compare-with"
                    name="with"
                    label="Other result"
                    defaultValue={other?.result_id ?? ""}
                  >
                    <option value="">Choose a result</option>
                    {all
                      .filter((item) => item.resultId !== result.result_id)
                      .map((item) => (
                        <option key={item.resultId} value={item.resultId}>
                          {item.title}
                        </option>
                      ))}
                  </SelectField>
                </div>
                <Button type="submit" variant="secondary">
                  Compare
                </Button>
              </Form>
              {other && check ? (
                <div className="mt-6 flex flex-col gap-4">
                  {check.compatible ? (
                    <>
                      <Alert tone="success" title="Comparable">
                        Same company, cutoff, currency and horizon.
                        {check.pairedBaselines
                          ? " The seed is the same too, so both baselines are the same paths."
                          : ""}
                      </Alert>
                      <CompareTable result={other} caption={other.title} />
                    </>
                  ) : (
                    <Alert tone="negative" title="Comparison blocked">
                      <ul className="list-disc pl-5">
                        {check.reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                      <p className="mt-2">
                        Results are never realigned silently. Choose a result with the same footing.
                      </p>
                    </Alert>
                  )}
                </div>
              ) : null}
            </Section>
          </div>
          <aside className="flex max-w-3xl flex-col items-start gap-4">
            <ResultNotClaims />
            <ButtonLink href={`/timeline/${result.result_id}`} variant="secondary">
              Open the timeline
            </ButtonLink>
          </aside>
        </div>
      )}
    </>
  );
}
