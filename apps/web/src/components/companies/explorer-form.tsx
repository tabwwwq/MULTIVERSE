"use client";

import Form from "next/form";
import { useRef } from "react";
import { COMPANY_STATUSES, SECTOR_LABELS, STATUS_LABELS, countryName } from "@/companies/labels";
import { COVERAGE_FILTERS, type CoverageFilter, type ExplorerQuery } from "@/companies/params";
import type { CompanyFacets } from "@/companies/repository";
import { MAX_QUERY_LENGTH } from "@/companies/search";
import { Button, ButtonLink } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/field";

/*
 * Search form. It is a plain GET form, so search works without JavaScript; with
 * JavaScript the results update while typing (debounced) and when a filter changes,
 * through client-side navigation that keeps focus in the field.
 */

interface ExplorerFormProps {
  query: ExplorerQuery;
  facets: CompanyFacets;
}

export function ExplorerForm({ query, facets }: ExplorerFormProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const timer = useRef<number | undefined>(undefined);

  const submitNow = () => {
    window.clearTimeout(timer.current);
    formRef.current?.requestSubmit();
  };
  const submitSoon = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => formRef.current?.requestSubmit(), 300);
  };

  return (
    <Form
      ref={formRef}
      action="/universe"
      replace
      scroll={false}
      role="search"
      aria-label="Companies"
      className="grid gap-4 rounded-panel border border-line bg-surface p-4 md:grid-cols-2 md:p-6 xl:grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))]"
    >
      <div className="md:col-span-2 xl:col-span-1">
        <TextField
          id="explorer-q"
          name="q"
          type="search"
          label="Search"
          hint="Ticker, company name or CIK. Former tickers and names count too."
          defaultValue={query.q}
          maxLength={MAX_QUERY_LENGTH}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="search"
          onChange={submitSoon}
        />
      </div>
      <SelectField
        id="explorer-sector"
        name="sector"
        label="Sector"
        defaultValue={query.sector ?? ""}
        onChange={submitNow}
      >
        <option value="">All sectors</option>
        {facets.sectors.map((sector) => (
          <option key={sector} value={sector}>
            {SECTOR_LABELS[sector]}
          </option>
        ))}
      </SelectField>
      <SelectField
        id="explorer-country"
        name="country"
        label="Country"
        defaultValue={query.country ?? ""}
        onChange={submitNow}
      >
        <option value="">All countries</option>
        {facets.countries.map((country) => (
          <option key={country} value={country}>
            {countryName(country)}
          </option>
        ))}
      </SelectField>
      <SelectField
        id="explorer-status"
        name="status"
        label="Lifecycle"
        defaultValue={query.status ?? ""}
        onChange={submitNow}
      >
        <option value="">Any lifecycle</option>
        {COMPANY_STATUSES.map((status) => (
          <option key={status} value={status}>
            {STATUS_LABELS[status]}
          </option>
        ))}
      </SelectField>
      <SelectField
        id="explorer-coverage"
        name="coverage"
        label="Revenue history"
        defaultValue={query.coverage ?? ""}
        onChange={submitNow}
      >
        <option value="">Any coverage</option>
        {(Object.keys(COVERAGE_FILTERS) as CoverageFilter[]).map((filter) => (
          <option key={filter} value={filter}>
            {COVERAGE_FILTERS[filter]}
          </option>
        ))}
      </SelectField>
      <div className="flex flex-wrap gap-3 md:col-span-2 xl:col-span-5">
        <Button type="submit" size="sm">
          Search
        </Button>
        <ButtonLink href="/universe" variant="ghost" size="sm">
          Clear search and filters
        </ButtonLink>
      </div>
    </Form>
  );
}
