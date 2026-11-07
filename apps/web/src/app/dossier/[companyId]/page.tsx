import { GitBranchPlus } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SECTOR_LABELS } from "@/companies/labels";
import { type RawParams, parseDossierParams } from "@/companies/params";
import { buildDossierView, cutoffChoices, dateOnly } from "@/companies/pit";
import { realCompany, realData } from "@/companies/real-data";
import { getCompanyRepository } from "@/companies/repository";
import { currentListing, currentName } from "@/companies/search";
import {
  LifecycleBadge,
  SupportBadge,
  SyntheticBadge,
} from "@/components/companies/company-badges";
import { ForecastPanel } from "@/components/companies/forecast-panel";
import { KeyFigures } from "@/components/companies/key-figures";
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
import { ButtonLink } from "@/components/ui/button";
import { decisionsHref } from "@/decisions/params";
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
  const record = realCompany(companyId);
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
            {record ? (
              <Badge tone="mint">
                #{record.evidence.rank} by public float, {record.evidence.float_as_of}
              </Badge>
            ) : (
              <SyntheticBadge />
            )}
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

      {hasFinancials ? <KeyFigures view={view} currency={company.reporting_currency} /> : null}

      {hasFinancials ? (
        <div className="mb-10">
          <ButtonLink
            href={decisionsHref(
              company.company_id,
              asOf !== null && cutoffChoices(dossier).includes(asOf) ? asOf : null,
            )}
            variant="secondary"
          >
            <GitBranchPlus aria-hidden="true" />
            Build a decision for this company
          </ButtonLink>
        </div>
      ) : null}

      {record?.forecast ? (
        <Section
          id="forecast"
          title="Model forecast"
          intro={`From the filings public on ${dateOnly(dossier.as_of)}. p50 is the middle of the model's range.`}
        >
          <ForecastPanel
            dossier={dossier}
            forecast={record.forecast}
            id={realData()?.index.forecast_id ?? null}
          />
        </Section>
      ) : null}
      {record && !record.forecast ? (
        <Section id="forecast" title="Model forecast">
          <p className="max-w-prose text-body text-ink-muted">{record.forecast_note}</p>
        </Section>
      ) : null}

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
          items={
            record
              ? [
                  "Values come from SEC filings; EBITDA and net debt are calculated from them.",
                  "The rank uses public float, not market capitalization or a share price.",
                  "A forecast is a research output of a model, not advice.",
                  "Missing values are not zero, and nothing is converted between currencies.",
                ]
              : [
                  "This is not a real company: every name, ticker, CIK and figure is synthetic.",
                  "Values are not forecasts or scenarios; they stand in for reported history.",
                  "Missing values are not zero, and nothing is converted between currencies.",
                ]
          }
        />
      </div>
    </>
  );
}
