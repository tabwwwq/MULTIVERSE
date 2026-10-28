import type { Metadata } from "next";
import { ResultList } from "@/components/results/result-list";
import { Alert } from "@/components/ui/alert";
import { PageHeader } from "@/layouts/page-header";
import { getResultRepository } from "@/results/repository";

export const metadata: Metadata = { title: "Universe Compare" };

export default async function CompareIndexPage() {
  const results = await getResultRepository().list();
  return (
    <>
      <PageHeader
        title="Universe Compare"
        summary="Scenarios side by side: KPIs at the horizon, waterfalls from the baseline and the distribution of paired differences."
      />
      <div className="mb-8 max-w-3xl">
        <Alert tone="info" title="Mock results only">
          The scenarios are fixed mock runs on synthetic companies until the Monte Carlo engine
          exists (Stage 22).
        </Alert>
      </div>
      <h2 className="mb-4 font-display text-h3 text-ink">Choose a result</h2>
      <ResultList results={results} basePath="/compare" />
    </>
  );
}
