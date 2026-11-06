"use client";

import type { ValuationReport } from "@multiverse/contracts";
import { Button } from "@/components/ui/button";
import { downloadText } from "@/lib/download";
import { stressCsv } from "@/valuation/dcf";

export function StressDownload({ report }: { report: ValuationReport }) {
  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      onClick={() =>
        downloadText("multiverse_stress_MODEL.csv", stressCsv(report), "text/csv;charset=utf-8")
      }
    >
      Download stress cases as CSV
    </Button>
  );
}
