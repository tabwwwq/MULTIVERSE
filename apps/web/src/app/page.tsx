import type { DataOrigin, ValueKind } from "@multiverse/contracts";
import Link from "next/link";
import { realData } from "@/companies/real-data";
import { TimelineMotif } from "@/components/brand/timeline-motif";
import { ChartLegend } from "@/components/charts/chart-legend";
import { LargestCompanies } from "@/components/overview/largest-companies";
import { SourceBadge } from "@/components/trust/source-badge";
import { TrustHeader } from "@/components/trust/trust-header";
import { ButtonLink } from "@/components/ui/button";
import { Section } from "@/layouts/page-header";

const VALUE_KINDS: ReadonlyArray<{ kind: ValueKind; origin: DataOrigin; text: string }> = [
  {
    kind: "observed",
    origin: "empirical",
    text: "Reported in an official filing, shown only from the day it was published.",
  },
  {
    kind: "forecast",
    origin: "empirical",
    text: "Produced by a model trained on point-in-time history, with its measured error.",
  },
  {
    kind: "simulated",
    origin: "empirical",
    text: "One of many paths from a scenario run, under an assumed model: a share of paths, not a probability of the world.",
  },
];

const NOT_CLAIMED = [
  "That an alternative company history is proven. Scenarios are conditional on stated assumptions.",
  "That an accurate forecast proves the effect of a decision. Prediction and cause are measured separately.",
  "That a p10 to p90 band holds the real outcome 80% of the time. The bands of the forecast held 82% for revenue growth on past years; simulation bands are not calibrated at all.",
  "A share price, a fair market value or investment advice.",
];

const JOURNEY: ReadonlyArray<{ title: string; text: string; href: string; action: string }> = [
  {
    title: "Find a company",
    text: "Search the 500 largest SEC filers by name, ticker or CIK.",
    href: "/universe",
    action: "Open the Universe Explorer",
  },
  {
    title: "See what was known",
    text: "Its quarters from the filings, and what was public on any past date.",
    href: "/time-machine",
    action: "Open the Time Machine",
  },
  {
    title: "Define a decision",
    text: "R&D, staff, an acquisition, an exit, capacity or new debt, with ranges.",
    href: "/decisions",
    action: "Open the Decision Builder",
  },
  {
    title: "Run it",
    text: "Paired paths with and without the decision, on this computer.",
    href: "/monitor",
    action: "Open the Simulation Monitor",
  },
  {
    title: "Read the report",
    text: "Every number with its source, in Markdown, CSV or print.",
    href: "/reports",
    action: "Open Report Studio",
  },
];

const PHASES: ReadonlyArray<{ name: string; stages: string; status: string }> = [
  {
    name: "Product and interface foundation",
    stages: "Stages 01 to 08",
    status: "Done",
  },
  {
    name: "Point-in-time data from SEC, Treasury, ECB and World Bank",
    stages: "Stages 09 to 14",
    status: "Done, the 500 largest filers are in the app",
  },
  {
    name: "Baselines, temporal neural networks and calibration",
    stages: "Stages 15 to 18",
    status: "Done, research only",
  },
  {
    name: "Decision registry, causal research, finance and Monte Carlo",
    stages: "Stages 19 to 23",
    status: "Done, results are conditional",
  },
  {
    name: "Security, reports and publication",
    stages: "Stages 24 to 26",
    status: "Done, released as v2.0.0-research",
  },
];

export default function OverviewPage() {
  const real = realData();
  const rows = real?.index.companies ?? [];
  const ranked = [...rows].sort((a, b) => a.evidence.rank - b.evidence.rank);
  const stats = real
    ? [
        { value: rows.length, label: "companies ranked from their 10-K covers" },
        { value: rows.filter((row) => row.has_forecast).length, label: "with a research forecast" },
        { value: rows.filter((row) => row.has_case).length, label: "ready to run a decision" },
      ]
    : [];
  return (
    <>
      <section
        aria-labelledby="hero-title"
        className="grid items-center gap-10 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
      >
        <div className="flex max-w-prose flex-col gap-6">
          <h1
            id="hero-title"
            className="font-display text-h1 font-semibold tracking-tight text-ink md:text-display"
          >
            What if business took another path?
          </h1>
          <p className="text-lead text-ink-muted">
            Choose a company, a date in its past and a decision it could have taken. MULTIVERSE
            builds the scenarios that follow and keeps the sources, assumptions and uncertainty
            behind every number in view.
          </p>
          <div className="flex flex-wrap gap-3">
            <ButtonLink href="/universe">Start with a company</ButtonLink>
            <ButtonLink href="/methodology" variant="secondary">
              Read the methodology
            </ButtonLink>
          </div>
          {stats.length > 0 ? (
            <dl className="grid grid-cols-3 gap-4 border-t border-line pt-6">
              {stats.map((stat) => (
                <div key={stat.label} className="flex flex-col gap-1">
                  <dt className="order-2 text-small text-ink-muted">{stat.label}</dt>
                  <dd className="order-1 font-display text-h2 text-ink tabular-nums">
                    {stat.value}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
        {ranked.length > 0 ? (
          <LargestCompanies rows={ranked.slice(0, 12)} />
        ) : (
          <figure className="rounded-frame border border-line bg-surface p-4 md:p-6">
            <TimelineMotif />
            <figcaption className="mt-4 flex flex-col gap-3 border-t border-line pt-4">
              <ChartLegend />
              <p className="text-micro text-ink-muted">
                Illustration of the chart language. Not data.
              </p>
            </figcaption>
          </figure>
        )}
      </section>

      <Section
        id="journey"
        title="From a company to a report"
        intro="Five steps, each on its own page. A decision can start from any company, and every finished run gets its report."
      >
        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {JOURNEY.map((step, index) => (
            <li key={step.title} className="flex">
              <Link
                href={step.href}
                className="group flex w-full flex-col gap-3 rounded-panel border border-line bg-surface p-5 hover:border-line-strong"
              >
                <span className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="flex size-8 shrink-0 items-center justify-center rounded-full border border-mint/50 text-small text-mint tabular-nums"
                  >
                    {index + 1}
                  </span>
                  <span className="font-medium text-ink">{step.title}</span>
                </span>
                <span className="text-small text-ink-muted">{step.text}</span>
                <span className="mt-auto text-small text-mint group-hover:underline">
                  {step.action}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        id="trust"
        title="Every result says how far to trust it"
        intro="Each scenario result opens with the same six facts, so a number never travels without its context."
      >
        <TrustHeader
          mode="demo"
          evidence="Synthetic fixture, no sources"
          asOf="2022-12-31"
          model="None, demo formulas"
          uncertainty="conditional_model_quantiles"
          calibrated={false}
          auditId="demo-0001"
        />
        <p className="mt-2 text-micro text-ink-muted">Example header filled with demo values.</p>
        <dl className="mt-8 grid gap-6 md:grid-cols-3">
          {VALUE_KINDS.map(({ kind, origin, text }) => (
            <div key={kind} className="flex flex-col gap-2">
              <dt>
                <SourceBadge kind={kind} origin={origin} />
              </dt>
              <dd className="text-small text-ink-muted">{text}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section id="not-claimed" title="What MULTIVERSE will not claim">
        <ul className="flex max-w-prose list-disc flex-col gap-2 pl-5 text-body text-ink-muted marker:text-ink-muted">
          {NOT_CLAIMED.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>

      <Section
        id="progress"
        title="Build progress"
        intro="The platform was built in 26 stages, each reviewed before the next began. All 26 are done."
      >
        <ol className="flex max-w-3xl flex-col">
          {PHASES.map((phase, index) => (
            <li
              key={phase.name}
              className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-4 border-t border-line py-4 first:border-t-0"
            >
              <span className="font-display text-h4 text-ink-muted tabular-nums" aria-hidden="true">
                {String.fromCharCode(65 + index)}
              </span>
              <div className="flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between md:gap-6">
                <span className="text-body text-ink">
                  <span className="sr-only">Phase {String.fromCharCode(65 + index)}: </span>
                  {phase.name}
                </span>
                <span className="text-small text-ink-muted tabular-nums md:whitespace-nowrap">
                  {phase.stages}, {phase.status.toLowerCase()}
                </span>
              </div>
            </li>
          ))}
        </ol>
      </Section>
    </>
  );
}
