import type { Metadata } from "next";
import { type RawParams, parseExplorerParams } from "@/companies/params";
import { getCompanyRepository } from "@/companies/repository";
import { CompanyResult } from "@/components/companies/company-result";
import { ExplorerForm } from "@/components/companies/explorer-form";
import { SyntheticBadge } from "@/components/companies/company-badges";
import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Universe Explorer" };

interface PageProps {
  searchParams: Promise<RawParams>;
}

export default async function UniversePage({ searchParams }: PageProps) {
  const { query, ignored, shortened } = parseExplorerParams(await searchParams);
  const repository = getCompanyRepository();
  const [hits, facets] = await Promise.all([repository.search(query), repository.facets()]);
  const filtered =
    query.q !== "" || query.sector || query.country || query.status || query.coverage;

  return (
    <>
      <PageHeader
        title="Universe Explorer"
        summary="Find a company by ticker, name or CIK, then open its dossier."
        meta={<SyntheticBadge />}
      />
      <div className="mb-6 flex max-w-3xl flex-col gap-3">
        <Alert tone="warning" title="Demo universe of seven fictional companies">
          Names, tickers, CIKs and figures are invented to show how the explorer behaves. Real
          companies arrive with SEC data in Stage 10.
        </Alert>
        {ignored.length > 0 ? (
          <Alert tone="info" title="Some filters in the link were ignored">
            Unsupported values for: {ignored.join(", ")}.
          </Alert>
        ) : null}
        {shortened ? (
          <Alert tone="info" title="Search text was shortened to 64 characters" />
        ) : null}
      </div>

      <ExplorerForm query={query} facets={facets} />

      <section aria-labelledby="results-title" className="mt-8">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="results-title" className="font-display text-h3 font-semibold text-ink">
            Companies
          </h2>
          <p role="status" className="text-small text-ink-muted tabular-nums">
            {hits.length} of {facets.total} companies
          </p>
        </div>
        {hits.length === 0 ? (
          <div className="flex max-w-prose flex-col items-start gap-4 rounded-panel border border-dashed border-line-strong p-6">
            <p className="font-medium text-ink">
              {query.q ? `No company matches “${query.q}”` : "No company matches these filters"}
            </p>
            <p className="text-body text-ink-muted">
              The demo universe holds seven fictional companies, so real tickers such as AAPL are
              not found yet. Try another ticker, a company name or a CIK, or remove filters.
            </p>
            {filtered ? (
              <ButtonLink href="/universe" variant="secondary" size="sm">
                Clear search and filters
              </ButtonLink>
            ) : null}
          </div>
        ) : (
          <ul className="grid gap-4 lg:grid-cols-2">
            {hits.map((hit) => (
              <li key={hit.company.company_id}>
                <CompanyResult hit={hit} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
