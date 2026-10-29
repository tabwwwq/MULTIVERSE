import type { Metadata } from "next";
import { getCompanyRepository } from "@/companies/repository";
import { currentListing, currentName } from "@/companies/search";
import { NotebookApp } from "@/components/notebook/notebook-app";
import { PageHeader } from "@/layouts/page-header";
import type { CompanyNames } from "@/notebook/model";

export const metadata: Metadata = { title: "Research Notebook" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function NotebookPage({ searchParams }: PageProps) {
  const requested = (await searchParams)["scenario"];
  // Only a well-formed ID is passed on; whether it exists is known on the device.
  const initialScenario = typeof requested === "string" && UUID.test(requested) ? requested : null;
  const repository = getCompanyRepository();
  const hits = await repository.search({
    q: "",
    sector: null,
    country: null,
    status: null,
    coverage: null,
  });
  const companies: CompanyNames = Object.fromEntries(
    hits.map(({ company }) => [
      company.company_id,
      { name: currentName(company).name, ticker: currentListing(company)?.ticker ?? null },
    ]),
  );
  return (
    <>
      <PageHeader
        title="Research Notebook"
        summary="Saved scenarios with names, tags and notes, every revision kept, reports that never change after export."
      />
      <NotebookApp companies={companies} initialScenario={initialScenario} />
    </>
  );
}
