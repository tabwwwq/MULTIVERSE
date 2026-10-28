import type { Metadata } from "next";
import { ResultList } from "@/components/results/result-list";
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
      <div className="mb-8 max-w-3xl">
        <Alert tone="info" title="Mock results only">
          Until the Monte Carlo engine exists (Stage 22), these are fixed mock runs on synthetic
          companies, built to test the charts. They are not forecasts.
        </Alert>
      </div>
      <h2 className="mb-4 font-display text-h3 text-ink">Choose a result</h2>
      <ResultList results={results} basePath="/timeline" />
    </>
  );
}
