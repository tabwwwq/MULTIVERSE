import type { Metadata } from "next";
import { ResultList } from "@/components/results/result-list";
import { MyRuns } from "@/components/simulation/my-runs";
import { Alert } from "@/components/ui/alert";
import { PageHeader } from "@/layouts/page-header";
import { getResultRepository } from "@/results/repository";

export const metadata: Metadata = { title: "Timeline Explorer" };

export default async function TimelineIndexPage() {
  const results = await getResultRepository().list();
  return (
    <>
      <PageHeader
        title="Timeline Explorer"
        summary="Observed history, a baseline and alternative paths with p10 to p90 bands, for one company at a knowledge cutoff."
      />
      <h2 className="mb-4 font-display text-h3 text-ink">Your runs</h2>
      <div className="mb-10 max-w-3xl">
        <MyRuns />
      </div>
      <h2 className="mb-4 font-display text-h3 text-ink">Examples</h2>
      <div className="mb-6 max-w-3xl">
        <Alert tone="info" title="Fixed examples on fictional companies">
          These runs are built to show the charts. They are not forecasts. Real companies are in the
          Universe Explorer, and a run of your own decision appears above.
        </Alert>
      </div>
      <ResultList results={results} basePath="/timeline" />
    </>
  );
}
