import type {
  AccountingStandard,
  CompanyStatus,
  LineageMethod,
  Sector,
  SupportStatus,
} from "@multiverse/contracts";

export const SECTOR_LABELS: Record<Sector, string> = {
  semiconductors: "Semiconductors",
  software: "Software",
  medical_devices: "Medical devices",
  utilities: "Utilities",
  logistics: "Logistics",
  instruments: "Instruments",
  industrial_machinery: "Industrial machinery",
};

export const SECTORS = Object.keys(SECTOR_LABELS) as Sector[];

export const STATUS_LABELS: Record<CompanyStatus, string> = {
  active: "Active",
  acquired: "Acquired",
  delisted: "Delisted",
  bankrupt: "Bankrupt",
};

export const COMPANY_STATUSES = Object.keys(STATUS_LABELS) as CompanyStatus[];

export const SUPPORT_LABELS: Record<SupportStatus, string> = {
  supported: "Supported",
  insufficient_history: "Insufficient history",
  unsupported: "Not supported",
};

export const ACCOUNTING_LABELS: Record<AccountingStandard, string> = {
  us_gaap: "US GAAP",
  ifrs: "IFRS",
};

export const METHOD_LABELS: Record<LineageMethod, string> = {
  reported: "Reported for the quarter",
  ytd_to_quarter: "Year-to-date figure converted to the quarter",
  fy_minus_nine_months: "Fiscal year minus the first nine months",
  calculated: "Calculated from reported items",
};

export interface MetricDefinition {
  slug: string;
  label: string;
  description: string;
}

/** The five metrics of the dossier (PRD §9, metric definitions). Order is the column order. */
export const DOSSIER_METRICS: readonly MetricDefinition[] = [
  { slug: "revenue", label: "Revenue", description: "Revenue as reported." },
  {
    slug: "ebitda_calculated",
    label: "EBITDA (calculated)",
    description: "Operating income plus depreciation and amortization. Not adjusted EBITDA.",
  },
  {
    slug: "fcf_simple",
    label: "FCF (CFO − CAPEX)",
    description: "Operating cash flow minus capital expenditure. Not free cash flow to the firm.",
  },
  {
    slug: "net_debt",
    label: "Net debt",
    description: "Interest-bearing debt minus cash at period end. A negative value is net cash.",
  },
  { slug: "rnd_expense", label: "R&D expense", description: "Research and development expense." },
];

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

export function countryName(code: string): string {
  return regionNames.of(code) ?? code;
}
