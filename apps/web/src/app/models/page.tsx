import type { Metadata } from "next";
import { JobBoard } from "@/components/models/job-board";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { PageHeader, Section } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Model Observatory" };

const APPROVED_PAIRS = ["Operating margin, 8 quarters", "EBITDA margin, 4 and 8 quarters"];

export default function ModelsPage() {
  return (
    <>
      <PageHeader
        title="Model Observatory"
        summary="Training jobs as they run, and what the evaluation measured. No forecast in this app comes from a model yet."
        meta={<Badge tone="violet">Research only</Badge>}
      />
      <Section
        id="jobs"
        title="Training jobs"
        intro="A job starts only after its estimate is approved, and keeps running when this page closes."
      >
        <JobBoard />
      </Section>
      <Section
        id="candidate"
        title="Model candidate"
        intro="Measured on years never used for a choice, under a protocol written before scoring."
      >
        <Alert tone="warning" title="Not approved for the product">
          <p>
            Candidate <code>model-20261028-9ce4d4180aa9</code>: the owner has not signed it off, and
            only 3 of 15 target and horizon pairs passed the rule.
          </p>
          <ul className="mt-2 list-disc pl-5">
            {APPROVED_PAIRS.map((pair) => (
              <li key={pair}>{pair}</li>
            ))}
          </ul>
        </Alert>
      </Section>
    </>
  );
}
