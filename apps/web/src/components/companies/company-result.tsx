import type { RealCompanyRow } from "@multiverse/contracts";
import { Check, Minus } from "lucide-react";
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

const MATCH_TEXT: Record<CompanyMatch["field"], string> = {
  cik: "Matched CIK",
  ticker: "Matched ticker",
  former_ticker: "Matched former ticker",
  name: "Matched name",
  former_name: "Matched former name",
};

function floatText(value: number): string {
  return value >= 1e12 ? `$${(value / 1e12).toFixed(2)}T` : `$${(value / 1e9).toFixed(1)}B`;
}

function matchDescription(match: CompanyMatch): string {
  const until =
    match.until && match.field.startsWith("former") ? `, used until ${match.until}` : "";
  return `${MATCH_TEXT[match.field]} ${match.value}${until}`;
}

function Ready({ ok, label }: { ok: boolean; label: string }) {
  const Icon = ok ? Check : Minus;
  return (
    <span className={`flex items-center gap-1.5 text-small ${ok ? "text-ink" : "text-ink-muted"}`}>
      <Icon aria-hidden="true" className={`size-4 ${ok ? "text-mint" : ""}`} />
      {label}
      <span className="sr-only">{ok ? ": yes" : ": no"}</span>
    </span>
  );
}

interface CompanyResultProps {
  hit: CompanyHit;
  /** Public float of the largest company, for the length of the bar. */
  largestFloat?: number;
  /** What exists for a real company: a forecast, a case to run. */
  real?: RealCompanyRow | undefined;
}

export function CompanyResult({ hit, largestFloat, real }: CompanyResultProps) {
  const { company, match } = hit;
  const listing = currentListing(company);
  const share = hit.evidence && largestFloat ? hit.evidence.public_float_usd / largestFloat : null;
  return (
    <article className="flex h-full flex-col gap-4 rounded-panel border border-line bg-surface p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {hit.evidence ? (
            <span
              className="mt-1 min-w-9 rounded-control border border-mint/40 px-1.5 py-0.5 text-center text-small text-mint tabular-nums"
              title="Rank by public float"
            >
              {hit.evidence.rank}
            </span>
          ) : null}
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
              {", "}
              {SECTOR_LABELS[company.sector]}, {countryName(company.country)}
            </p>
            {match && match.field !== "ticker" && match.field !== "name" ? (
              <p className="text-small text-blue">{matchDescription(match)}</p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {hit.evidence ? null : <SyntheticBadge />}
          <SupportBadge status={hit.supportStatus} />
          <LifecycleBadge company={company} />
        </div>
      </div>

      {hit.evidence && share !== null ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-2 text-small">
            <span className="text-ink-muted">Public float, {hit.evidence.float_as_of}</span>
            <span className="text-ink tabular-nums">
              {floatText(hit.evidence.public_float_usd)}
            </span>
          </div>
          <div aria-hidden="true" className="h-1.5 overflow-hidden rounded-pill bg-inset">
            <div
              className="h-full rounded-pill bg-mint/80"
              style={{ width: `${Math.max(share * 100, 1.5)}%` }}
            />
          </div>
        </div>
      ) : null}

      <div className="mt-auto flex flex-col gap-3">
        <CoverageMeter
          label="Revenue history"
          valid={hit.revenueCoverage?.quarters_valid ?? 0}
          expected={hit.revenueCoverage?.quarters_expected ?? 0}
        />
        {real ? (
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            <Ready ok={real.has_forecast} label="Research forecast" />
            <Ready ok={real.has_case} label="Ready to run" />
          </div>
        ) : null}
      </div>
    </article>
  );
}
