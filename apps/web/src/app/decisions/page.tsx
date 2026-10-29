import type { Metadata } from "next";
import Link from "next/link";
import type { RawParams } from "@/companies/params";
import { cutoffChoices } from "@/companies/pit";
import { getCompanyRepository } from "@/companies/repository";
import { currentListing, currentName } from "@/companies/search";
import { SupportBadge, SyntheticBadge } from "@/components/companies/company-badges";
import { DecisionBuilder } from "@/components/decisions/decision-builder";
import { RestoreGate } from "@/components/notebook/restore-gate";
import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { buildCompanyContext } from "@/decisions/context";
import { decisionsHref, parseDecisionParams } from "@/decisions/params";
import { PageHeader } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Decision Builder" };

interface PageProps {
  searchParams: Promise<RawParams>;
}

const SUMMARY =
  "Define one management decision for one company at a knowledge cutoff: its size and unit, timing, costs, financing and the ranges behind it.";

export default async function DecisionsPage({ searchParams }: PageProps) {
  const repository = getCompanyRepository();
  const ids = await repository.listIds();
  const dossiers = new Map(
    (await Promise.all(ids.map((id) => repository.getDossier(id))))
      .filter((dossier) => dossier !== null)
      .map((dossier) => [dossier.company.company_id, dossier]),
  );
  const { companyId, asOf, type, restore, ignored } = parseDecisionParams(
    await searchParams,
    ids,
    (id) => {
      const dossier = dossiers.get(id);
      return dossier ? cutoffChoices(dossier) : [];
    },
  );
  const dossier = companyId ? dossiers.get(companyId) : undefined;
  const context = dossier ? buildCompanyContext(dossier) : null;

  const ignoredAlert =
    ignored.length > 0 ? (
      <Alert tone="warning" title="Some values in the link were ignored">
        Unsupported values for: {ignored.join(", ")}.
      </Alert>
    ) : null;

  if (!context) {
    const hits = await repository.search({
      q: "",
      sector: null,
      country: null,
      status: null,
      coverage: null,
    });
    return (
      <>
        <PageHeader title="Decision Builder" summary={SUMMARY} meta={<SyntheticBadge />} />
        <div className="mb-8 flex max-w-3xl flex-col gap-4 empty:hidden">{ignoredAlert}</div>
        <h2 className="mb-4 font-display text-h3 text-ink">Choose a company</h2>
        <ul className="flex max-w-3xl flex-col divide-y divide-line rounded-panel border border-line bg-surface">
          {hits.map(({ company, supportStatus }) => (
            <li
              key={company.company_id}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
            >
              <Link
                href={decisionsHref(company.company_id)}
                className="rounded-control font-medium text-ink hover:text-mint"
              >
                {currentName(company).name}
                <span className="ml-2 text-small font-normal text-ink-muted tabular-nums">
                  {currentListing(company)?.ticker}
                </span>
              </Link>
              <SupportBadge status={supportStatus} />
            </li>
          ))}
        </ul>
      </>
    );
  }

  const initialAsOf = asOf ?? context.cutoffs[0]?.asOf ?? null;
  const unsupported = context.supportStatus === "unsupported";

  return (
    <>
      <PageHeader title="Decision Builder" summary={SUMMARY} meta={<SyntheticBadge />} />
      <div className="mb-8 flex max-w-3xl flex-col gap-4">
        {ignoredAlert}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-panel border border-line bg-surface px-4 py-3">
          <p className="text-body text-ink">
            <span className="text-ink-muted">Company: </span>
            <span className="font-medium">{context.name}</span>
            {context.ticker ? (
              <span className="ml-2 text-small text-ink-muted tabular-nums">{context.ticker}</span>
            ) : null}
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-small">
            <Link href="/decisions" className="rounded-control text-mint hover:underline">
              Change company
            </Link>
            <Link
              href={`/dossier/${context.companyId}`}
              className="rounded-control text-mint hover:underline"
            >
              Open dossier
            </Link>
          </div>
        </div>
        {unsupported ? (
          <Alert tone="negative" title="This company is not supported yet">
            {context.supportReason} A decision needs a supported company with US-GAAP filings.
          </Alert>
        ) : initialAsOf === null ? (
          <Alert tone="negative" title="No knowledge cutoff available">
            No quarter of this company has data yet.
          </Alert>
        ) : (
          <Alert tone="info" title="Demo only">
            The company and its figures are synthetic, and no model is calibrated. Validation checks
            the decision and translates it into dollars; it predicts nothing.
          </Alert>
        )}
      </div>
      {unsupported || initialAsOf === null ? (
        <ButtonLink href="/decisions" variant="secondary">
          Choose another company
        </ButtonLink>
      ) : restore ? (
        <RestoreGate
          context={context}
          initialAsOf={initialAsOf}
          initialType={type}
          restore={restore}
        />
      ) : (
        <DecisionBuilder context={context} initialAsOf={initialAsOf} initialType={type} />
      )}
    </>
  );
}
