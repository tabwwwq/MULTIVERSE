import type {
  AccessCategory,
  Authentication,
  DataFormat,
  DecisionStatus,
  DocKind,
  Evidence,
  FieldRole,
  FieldType,
  KeyStatus,
  Level,
  Redistribution,
  Resale,
  RiskCategory,
} from "@multiverse/contracts";
import { type DataSource, SOURCE_CATALOG } from "@multiverse/contracts/sources";

/*
 * The source catalog of Stage 09 and the words the interface uses for its codes.
 * Metadata only: nothing here downloads data or reads it from a provider.
 */

export { SOURCE_CATALOG };
export const SOURCES: readonly DataSource[] = SOURCE_CATALOG.sources;

export function sourceById(id: string): DataSource | undefined {
  return SOURCES.find((source) => source.source_id === id);
}

export const ACCESS_ORDER: readonly AccessCategory[] = ["public_access", "api_key", "licensed"];

export const ACCESS_LABELS: Record<AccessCategory, string> = {
  public_access: "Public access",
  api_key: "Free API key",
  licensed: "Licensed",
};

export const AUTHENTICATION_LABELS: Record<Authentication, string> = {
  none: "None",
  declared_user_agent: "Declared User-Agent with contact email",
  api_key: "Personal API key",
  contract: "Contract",
};

export const KEY_LABELS: Record<KeyStatus, string> = {
  not_required: "No key needed",
  owner_must_register: "Key needed: the owner registers",
  contract_required: "Contract needed",
};

export const REDISTRIBUTION_LABELS: Record<Redistribution, string> = {
  public_information: "Public information, citation requested",
  open_licence: "Open licence",
  reuse_with_conditions: "Free reuse with conditions",
  permission_required: "Permission of the data owner needed",
  not_allowed: "Not allowed",
};

export const RESALE_LABELS: Record<Resale, string> = {
  not_granted: "Not granted",
  allowed_by_licence: "Allowed by the licence",
  prohibited: "Prohibited",
};

export const DOC_KIND_LABELS: Record<DocKind, string> = {
  api_reference: "API reference",
  access_policy: "Access policy",
  terms: "Terms",
  dataset_page: "Dataset page",
  documentation: "Documentation",
};

export const FORMAT_LABELS: Record<DataFormat, string> = {
  json: "JSON",
  csv: "CSV",
  xml: "XML",
  sdmx_ml: "SDMX-ML",
  tsv: "TSV",
  zip: "ZIP",
  xlsx: "XLSX",
  json_stat: "JSON-stat",
  html: "HTML",
};

export const FIELD_TYPE_LABELS: Record<FieldType, string> = {
  string: "Text",
  integer: "Integer",
  decimal: "Decimal",
  date: "Date",
  datetime: "Date and time",
  code: "Code",
  boolean: "Yes or no",
  object: "Object",
  array: "List",
};

export const ROLE_LABELS: Record<FieldRole, string> = {
  identifier: "Identifier",
  period: "Period",
  knowledge_time: "Knowledge time",
  value: "Value",
  unit: "Unit",
  revision: "Revision",
  metadata: "Metadata",
};

export const DECISION_LABELS: Record<DecisionStatus, string> = {
  awaiting_owner_decision: "Downloads off, awaiting the owner's decision",
  approved: "Downloads approved by the owner",
  declined: "Downloads declined by the owner",
};

export const LEVEL_LABELS: Record<Level, string> = { low: "Low", medium: "Medium", high: "High" };

export const RISK_CATEGORY_LABELS: Record<RiskCategory, string> = {
  region_and_gaap: "Region and GAAP",
  survivorship: "Survivorship",
  missing_tags: "Missing XBRL tags",
  quarterization: "Quarterization",
  restatement: "Restatement",
  time_to_publication: "Time to publication",
  currency_and_scale: "Currency and scale",
  identifiers: "Identifiers",
  terms_of_use: "Terms of use",
  access: "Access",
  data_errors: "Data errors",
  revisions: "Revisions",
  volume: "Volume",
};

export const EVIDENCE_LABELS: Record<Evidence, string> = {
  verified: "Verified",
  expected: "Expected, to check",
};

export const PRIORITY_LABELS: Record<"p1" | "p2" | "p3" | "excluded", string> = {
  p1: "P1",
  p2: "P2",
  p3: "P3",
  excluded: "Excluded",
};

/** The highest possible candidate score: every criterion at 2 points. */
export const MAX_SCORE = SOURCE_CATALOG.rubric.reduce((sum, item) => sum + item.weight * 2, 0);
