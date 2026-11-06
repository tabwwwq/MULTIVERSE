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
        summary="Training jobs as they run, and what the evaluation measured. Only the research case of the Launch Center reads a model, for EBITDA margin."
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
        title="Signed model"
        intro="Measured on years never used for a choice, under a protocol written before scoring."
      >
        <Alert tone="warning" title="Not approved for the product">
          <p>
            Model <code>model-20261028-9ce4d4180aa9</code> is signed for research on the 3 of 15
            target and horizon pairs that passed the rule, and on nothing else.
          </p>
          <p className="mt-2">
            New training on its macro features is refused: the FRED terms forbid machine learning on
            FRED content, and the owner has not decided yet what replaces them.
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
