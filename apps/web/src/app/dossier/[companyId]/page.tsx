import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SECTOR_LABELS } from "@/companies/labels";
import { type RawParams, parseDossierParams } from "@/companies/params";
import { buildDossierView, dateOnly } from "@/companies/pit";
import { getCompanyRepository } from "@/companies/repository";
import { currentListing, currentName } from "@/companies/search";
import {
  LifecycleBadge,
  SupportBadge,
  SyntheticBadge,
} from "@/components/companies/company-badges";
import {
  CoverageList,
  DossierControls,
  FilingsTable,
  FinancialTable,
  IdentityList,
  ListingHistory,
  QualityFlags,
} from "@/components/companies/dossier-sections";
import { NotClaims } from "@/components/trust/not-claims";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { PageHeader, Section } from "@/layouts/page-header";

interface PageProps {
  params: Promise<{ companyId: string }>;
  searchParams: Promise<RawParams>;
}

// Only known company IDs render; anything else is a 404 (safe URL behaviour).
export const dynamicParams = false;

export async function generateStaticParams() {
  const ids = await getCompanyRepository().listIds();
  return ids.map((companyId) => ({ companyId }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const dossier = await getCompanyRepository().getDossier((await params).companyId);
  return dossier ? { title: currentName(dossier.company).name } : {};
}

export default async function CompanyDossierPage({ params, searchParams }: PageProps) {
  const { companyId } = await params;
  const dossier = await getCompanyRepository().getDossier(companyId);
  if (!dossier) notFound();

  const { company } = dossier;
  const { asOf, scale, ignored } = parseDossierParams(await searchParams, dateOnly(dossier.as_of));
  const view = buildDossierView(dossier, asOf);
  const listing = currentListing(company);
  const hasFinancials = dossier.support_status !== "unsupported";

  return (
    <>
      <PageHeader
        title={currentName(company).name}
        summary={
          listing
            ? `${listing.exchange}: ${listing.ticker}. ${SECTOR_LABELS[company.sector]}.`
            : SECTOR_LABELS[company.sector]
        }
        meta={
          <>
            <SyntheticBadge />
            <SupportBadge status={dossier.support_status} />
            <LifecycleBadge company={company} />
          </>
        }
      />

      <div className="mb-10 flex max-w-3xl flex-col gap-3 empty:hidden">
        {dossier.support_status === "unsupported" ? (
          <Alert tone="negative" title="This company is not supported yet">
            {dossier.support_reason}
          </Alert>
        ) : null}
        {dossier.support_status === "insufficient_history" ? (
          <Alert tone="warning" title="Insufficient history">
            {dossier.support_reason}
          </Alert>
        ) : null}
        {company.status !== "active" && company.status_note ? (
          <Alert tone="info" title={`Left the market on ${company.status_date}`}>
            {company.status_note}
          </Alert>
        ) : null}
        {ignored.length > 0 ? (
          <Alert tone="info" title="Some settings in the link were ignored">
            Unsupported values for: {ignored.join(", ")}. The latest snapshot in USD m is shown.
          </Alert>
        ) : null}
      </div>

      <Section id="identity" title="Identity">
        <IdentityList company={company} />
      </Section>

      <Section
        id="listing"
        title="Listing history"
        intro="The company ID never changes. Tickers and legal names are histories with dates."
      >
        <ListingHistory company={company} />
      </Section>

      {hasFinancials ? (
        <>
          <Section
            id="financials"
            title="Financial history"
            intro={
              view.isLatest
                ? "Values from filings published up to the snapshot date."
                : `Only filings published on or before ${view.cutoff}. ${view.notPublicCount} values were filed later and are marked as not public.`
            }
          >
            <div className="flex flex-col gap-6">
              <DossierControls companyId={companyId} dossier={dossier} asOf={asOf} scale={scale} />
              <FinancialTable dossier={dossier} view={view} scale={scale} />
              <div className="flex flex-wrap gap-2">
                <Badge>EBITDA is calculated, not reported</Badge>
                <Badge>FCF is CFO − CAPEX, not FCFF</Badge>
                <Badge>A dash means missing, never zero</Badge>
              </div>
            </div>
          </Section>

          <Section
            id="coverage"
            title="Coverage"
            intro="Fiscal quarters with a valid value at this cutoff."
          >
            <CoverageList view={view} />
          </Section>
        </>
      ) : null}

      <Section id="quality" title="Data quality">
        <QualityFlags dossier={dossier} />
      </Section>

      <Section id="filings" title="Filings">
        <FilingsTable filings={view.filings} />
      </Section>

      <div className="mt-16 max-w-3xl">
        <NotClaims
          items={[
            "This is not a real company: every name, ticker, CIK and figure is synthetic.",
            "Values are not forecasts or scenarios; they stand in for reported history.",
            "Missing values are not zero, and nothing is converted between currencies.",
          ]}
        />
      </div>
    </>
  );
}
