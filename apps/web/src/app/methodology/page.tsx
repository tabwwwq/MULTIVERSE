import type { ResultMode, UncertaintyType } from "@multiverse/contracts";
import type { Metadata } from "next";
import { InferenceModeBadge } from "@/components/trust/inference-mode-badge";
import { UNCERTAINTY_LABELS } from "@/components/trust/trust-header";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader, Section } from "@/layouts/page-header";

export const metadata: Metadata = { title: "Methodology" };

const LEVELS = [
  {
    name: "Descriptive",
    text: "What happened: R&D grew, and eight quarters later revenue changed. No claim about why.",
  },
  {
    name: "Predictive",
    text: "What a model trained on history expects, given the decision. It learns associations, not causes.",
  },
  {
    name: "Causal",
    text: "The effect of the decision itself, under assumptions that are written down and tested where possible. The most demanding level, and never assigned automatically.",
  },
];

const MODES: ReadonlyArray<{ mode: ResultMode; text: string }> = [
  {
    mode: "demo",
    text: "Synthetic data that shows how the mechanics work. It describes no real company.",
  },
  {
    mode: "empirical_forecast",
    text: "A model trained on point-in-time data with a measured out-of-time error.",
  },
  {
    mode: "causal_study",
    text: "A decision type whose identification diagnostics were run and stored.",
  },
  {
    mode: "fictional_exploratory",
    text: "A scenario with no observed precedent. Only a picture of its assumptions.",
  },
];

const UNCERTAINTY: ReadonlyArray<{ type: UncertaintyType; text: string }> = [
  { type: "none", text: "Observed values reported in a filing." },
  { type: "predictive_quantiles", text: "Spread of a forecast, before its coverage is measured." },
  {
    type: "conditional_model_quantiles",
    text: "Spread of simulated paths, valid only under the model's assumptions.",
  },
  {
    type: "calibrated_interval",
    text: "A band whose coverage was checked on held-out companies and dates.",
  },
];

interface SourceRow {
  source: string;
  provides: string;
  access: string;
}

const SOURCES: readonly SourceRow[] = [
  {
    source: "SEC EDGAR",
    provides: "Company filings and XBRL facts (10-K, 10-Q, 20-F)",
    access: "Public, fair-access rate limits",
  },
  {
    source: "FRED and ALFRED",
    provides: "US macro series with historical vintages",
    access: "Free API key",
  },
  { source: "ECB SDMX", provides: "Euro area rates, FX and indicators", access: "Public" },
  { source: "World Bank", provides: "Annual cross-country indicators", access: "Public" },
];

const LIMITATIONS = [
  "Corporate decisions are not random, so a difference after a decision is not its effect without a research design.",
  "Scenarios like a company without its flagship product have no observed ground truth and stay fictional.",
  "A good forecast error says nothing about the accuracy of an estimated policy effect.",
  "Coverage of companies and metrics is unknown until the data audit in Stage 14.",
];

export default function MethodologyPage() {
  return (
    <>
      <PageHeader
        title="Methodology"
        summary="How MULTIVERSE separates what happened, what a model expects and what a decision causes, and what it refuses to claim."
      />

      <Section id="levels" title="Three levels of conclusion">
        <ol className="flex max-w-prose flex-col gap-4">
          {LEVELS.map((level, index) => (
            <li key={level.name} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3">
              <span className="font-display text-h4 text-ink-muted tabular-nums" aria-hidden="true">
                {index + 1}
              </span>
              <div>
                <p className="font-medium text-ink">{level.name}</p>
                <p className="text-body text-ink-muted">{level.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        id="modes"
        title="Result modes"
        intro="Every result carries exactly one mode. The system assigns it from the available evidence; a user cannot raise it."
      >
        <dl className="flex max-w-prose flex-col gap-4">
          {MODES.map(({ mode, text }) => (
            <div
              key={mode}
              className="flex flex-col gap-1.5 sm:flex-row sm:items-baseline sm:gap-4"
            >
              <dt className="shrink-0 sm:w-48">
                <InferenceModeBadge mode={mode} />
              </dt>
              <dd className="text-body text-ink-muted">{text}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section id="uncertainty" title="Uncertainty">
        <dl className="flex max-w-prose flex-col gap-3">
          {UNCERTAINTY.map(({ type, text }) => (
            <div key={type}>
              <dt className="font-medium text-ink">{UNCERTAINTY_LABELS[type]}</dt>
              <dd className="text-body text-ink-muted">{text}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section
        id="pit"
        title="Point-in-time data"
        intro="A fact counts from the day it was filed or released, not from the end of the period it describes. A forecast made on 31 December 2021 never sees a filing first submitted in 2022, and later restatements never rewrite what was known earlier."
      >
        <DataTable<SourceRow>
          id="sources"
          caption="Official sources, in order of priority"
          rowKey={(row) => row.source}
          rows={SOURCES}
          columns={[
            { key: "source", header: "Source", rowHeader: true },
            { key: "provides", header: "Provides" },
            { key: "access", header: "Access" },
          ]}
        />
      </Section>

      <Section id="limitations" title="Known limitations">
        <ul className="flex max-w-prose list-disc flex-col gap-2 pl-5 text-body text-ink-muted">
          {LIMITATIONS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}
