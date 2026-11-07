import type { Metadata } from "next";
import { Suspense } from "react";
import { ReportStudio } from "@/components/reports/report-studio";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Report Studio" };

export default function ReportsPage() {
  return (
    <>
      <PageHeader
        title="Report Studio"
        summary="The research report of a finished run: sources, versions, assumptions and limitations, in Markdown, CSV or print, with a manifest that builds it again byte for byte."
        meta={<Badge tone="violet">Conditional, not validated</Badge>}
      />
      <Suspense fallback={<p className="text-body text-ink-muted">Reading the runs.</p>}>
        <ReportStudio />
      </Suspense>
    </>
  );
}
