import Link from "next/link";
import { SECTOR_LABELS, countryName } from "@/companies/labels";
import type { CompanyHit } from "@/companies/repository";
import type { CompanyMatch } from "@/companies/search";
import { currentListing, currentName } from "@/companies/search";
import {
  LifecycleBadge,
  SupportBadge,
  SyntheticBadge,
} from "@/components/companies/company-badges";
import { CoverageMeter } from "@/components/companies/coverage-meter";
import { Badge } from "@/components/ui/badge";

const MATCH_TEXT: Record<CompanyMatch["field"], string> = {
  cik: "Matched CIK",
  ticker: "Matched ticker",
  former_ticker: "Matched former ticker",
  name: "Matched name",
  former_name: "Matched former name",
};

function matchDescription(match: CompanyMatch): string {
  const until =
    match.until && match.field.startsWith("former") ? `, used until ${match.until}` : "";
  return `${MATCH_TEXT[match.field]} ${match.value}${until}`;
}

export function CompanyResult({ hit }: { hit: CompanyHit }) {
  const { company, match } = hit;
  const listing = currentListing(company);
  return (
    <article className="flex flex-col gap-4 rounded-panel border border-line bg-surface p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="font-display text-h4 font-semibold text-ink">
            <Link
              href={`/dossier/${company.company_id}`}
              className="rounded-control hover:text-mint"
            >
              {currentName(company).name}
            </Link>
          </h3>
          <p className="text-small text-ink-muted tabular-nums">
            {listing ? `${listing.exchange}: ${listing.ticker}` : "No listing"}
            {company.cik ? <>, CIK {company.cik}</> : null}
          </p>
          {match && match.field !== "ticker" && match.field !== "name" ? (
            <p className="text-small text-blue">{matchDescription(match)}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <SupportBadge status={hit.supportStatus} />
          <LifecycleBadge company={company} />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Badge>{SECTOR_LABELS[company.sector]}</Badge>
        <Badge>{countryName(company.country)}</Badge>
        <SyntheticBadge />
      </div>
      <CoverageMeter
        label="Revenue history"
        valid={hit.revenueCoverage?.quarters_valid ?? 0}
        expected={hit.revenueCoverage?.quarters_expected ?? 0}
      />
    </article>
  );
}
