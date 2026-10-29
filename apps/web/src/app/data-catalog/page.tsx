import type { Metadata } from "next";
import { Database } from "lucide-react";
import { SourceCard } from "@/components/sources/source-parts";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/field";
import { PageHeader, Section } from "@/layouts/page-header";
import { ACCESS_LABELS, ACCESS_ORDER, SOURCES, SOURCE_CATALOG } from "@/sources/catalog";
import { type RawParams, parseCatalogParams } from "@/sources/params";
import { MAX_CATALOG_QUERY, searchSources } from "@/sources/search";

export const metadata: Metadata = { title: "Data Catalog" };

interface PageProps {
  searchParams: Promise<RawParams>;
}

export default async function DataCatalogPage({ searchParams }: PageProps) {
  const { query, ignored, shortened } = parseCatalogParams(await searchParams);
  const hits = searchSources(SOURCES, query.q, query.access);
  const showLicensed = query.access === null || query.access === "licensed";

  return (
    <>
      <PageHeader
        title="Data Catalog"
        summary="Official sources, their terms, keys, request limits, revision rules and data dictionaries."
        meta={
          <>
            <Badge icon={Database}>Metadata only</Badge>
            <Badge tone="warning">Automatic downloads off</Badge>
          </>
        }
      />
      <div className="mb-6 flex max-w-3xl flex-col gap-3">
        <Alert tone="info" title="The catalog shows no source data">
          This catalog describes sources; the app holds none of their data. Each source stays off
          until the owner approves it, and what was downloaded stays in the local raw archive,
          outside the app and out of git. Documentation was checked on {SOURCE_CATALOG.verified_on};
          free access is not treated as a licence to resell.
        </Alert>
        {ignored.length > 0 ? (
          <Alert tone="info" title="Some filters in the link were ignored">
            Unsupported values for: {ignored.join(", ")}.
          </Alert>
        ) : null}
        {shortened ? (
          <Alert
            tone="info"
            title={`Search text was shortened to ${MAX_CATALOG_QUERY} characters`}
          />
        ) : null}
      </div>

      <form
        action="/data-catalog"
        method="get"
        role="search"
        aria-label="Sources"
        className="grid gap-4 rounded-panel border border-line bg-surface p-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] md:p-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] xl:items-start"
      >
        <TextField
          id="catalog-q"
          name="q"
          type="search"
          label="Search"
          hint="Source, dataset, identifier, format or field, for example vintage or CIK."
          defaultValue={query.q}
          maxLength={MAX_CATALOG_QUERY}
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="search"
        />
        <SelectField
          id="catalog-access"
          name="access"
          label="Access"
          defaultValue={query.access ?? ""}
        >
          <option value="">All access types</option>
          {ACCESS_ORDER.map((access) => (
            <option key={access} value={access}>
              {ACCESS_LABELS[access]}
            </option>
          ))}
        </SelectField>
        <div className="flex flex-wrap gap-3 md:col-span-2 xl:col-span-1 xl:mt-7">
          <Button type="submit">Search</Button>
          <ButtonLink href="/data-catalog" variant="secondary">
            Clear
          </ButtonLink>
        </div>
      </form>

      <section aria-labelledby="sources-title" className="mt-8">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="sources-title" className="font-display text-h3 font-semibold text-ink">
            Sources
          </h2>
          <p role="status" className="text-small text-ink-muted tabular-nums">
            {hits.length} of {SOURCES.length} sources
          </p>
        </div>
        {hits.length === 0 ? (
          <p className="max-w-prose rounded-panel border border-dashed border-line-strong p-6 text-body text-ink">
            {query.q ? `No source matches “${query.q}”.` : "No source has this access type."}
          </p>
        ) : (
          <div className="flex flex-col gap-8">
            {ACCESS_ORDER.map((access) => {
              const group = hits.filter((hit) => hit.source.access === access);
              if (group.length === 0) return null;
              return (
                <div key={access} className="flex flex-col gap-3">
                  <h3 className="text-small font-semibold tracking-wide text-ink-muted uppercase">
                    {ACCESS_LABELS[access]}
                  </h3>
                  <ul className="grid gap-4 lg:grid-cols-2">
                    {group.map((hit) => (
                      <li key={hit.source.source_id}>
                        <SourceCard source={hit.source} matches={hit.matches} />
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {showLicensed ? (
        <Section
          id="licensed"
          title="Licensed data"
          intro="Data that only a paid provider can supply. No provider is chosen; nothing is used before written terms."
        >
          <ul className="grid gap-4 lg:grid-cols-2">
            {SOURCE_CATALOG.licensed_needs.map((need) => (
              <li
                key={need.need_id}
                className="flex flex-col gap-2 rounded-panel border border-dashed border-line-strong p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="font-display text-h4 font-semibold text-ink">{need.title}</h3>
                  <Badge tone="violet">Not selected, {need.earliest_version} at the earliest</Badge>
                </div>
                <p className="text-small text-ink-muted">{need.why}</p>
                <p className="text-small text-ink-muted">
                  <span className="font-medium text-ink">Without it: </span>
                  {need.without_it}
                </p>
                <p className="text-small text-ink-muted">
                  <span className="font-medium text-ink">Needed first: </span>
                  {need.requirement}
                </p>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section
        id="plan"
        title="Risks, first companies and acquisition plan"
        intro="What can go wrong with these sources, which companies and sectors come first and why, and the steps that wait for the owner's decision."
      >
        <ButtonLink href="/data-catalog/plan" variant="secondary">
          Open the acquisition plan
        </ButtonLink>
      </Section>
    </>
  );
}
