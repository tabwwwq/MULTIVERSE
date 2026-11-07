import type { Metadata } from "next";
import { Suspense } from "react";
import { RunReport } from "@/components/simulation/run-report";
import { PageHeader } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Simulation result" };

export default function RunPage() {
  return (
    <>
      <PageHeader
        title="Simulation result"
        summary="Paired Monte Carlo paths of one company, with and without a decision."
      />
      <Suspense fallback={<p className="text-body text-ink-muted">Reading the result.</p>}>
        <RunReport />
      </Suspense>
    </>
  );
}
