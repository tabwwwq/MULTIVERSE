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
        summary="Training jobs as they run, and what the evaluation measured. The cases of runs read model margins: the Launch Center case from the signed model, real companies from the model without FRED."
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
      <Section
        id="real"
        title="Forecast of real companies"
        intro="A second model, trained without FRED, gives the forecasts on the dossiers of real companies."
      >
        <Alert tone="warning" title="Research only, not approved for the product">
          <p>
            A GRU with attention, chosen on the validation years 2016 to 2019, trained on SEC
            filings of 1,429 companies, U.S. Treasury yields and ECB rates (benchmark{" "}
            <code>bench-20261106-20302859cff2</code>).
          </p>
          <p className="mt-2">
            On the test years 2020 to 2026 its error on revenue growth over 4 quarters is 31.7%
            below persistence (29.9 to 33.4%) and 4.7% below the best simple model. Over 1 quarter
            it is 11.8% worse than gradient boosting. These are past years, not the accuracy of a
            forecast of today, whose outcome is not known yet.
          </p>
          <p className="mt-2">
            Its p10 to p90 ranges held 82.2% of outcomes for revenue growth over 4 quarters on 2024
            to 2026, against 80% stated. Under the approval rule of Stage 17, written before
            scoring, 2 of 15 target and horizon pairs pass: revenue growth over 4 and 8 quarters.
          </p>
        </Alert>
      </Section>
    </>
  );
}
