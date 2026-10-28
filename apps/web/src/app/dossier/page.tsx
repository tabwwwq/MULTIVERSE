import type { Metadata } from "next";
import Link from "next/link";
import { getCompanyRepository } from "@/companies/repository";
import { currentListing, currentName } from "@/companies/search";
import { SupportBadge, SyntheticBadge } from "@/components/companies/company-badges";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Company Dossier" };

export default async function DossierIndexPage() {
  const hits = await getCompanyRepository().search({
    q: "",
    sector: null,
    country: null,
    status: null,
    coverage: null,
  });

  return (
    <>
      <PageHeader
        title="Company Dossier"
        summary="Financial history, filings, fiscal calendar and data quality of one company. Pick a company, or search for one in the explorer."
        meta={<SyntheticBadge />}
      />
      <ul className="flex max-w-3xl flex-col divide-y divide-line rounded-panel border border-line bg-surface">
        {hits.map(({ company, supportStatus }) => (
          <li
            key={company.company_id}
            className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
          >
            <Link
              href={`/dossier/${company.company_id}`}
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
      <div className="mt-6">
        <ButtonLink href="/universe" variant="secondary">
          Search in the Universe Explorer
        </ButtonLink>
      </div>
    </>
  );
}
