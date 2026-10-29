import type { DataOrigin, ValueKind } from "@multiverse/contracts";
import { TimelineMotif } from "@/components/brand/timeline-motif";
import { ChartLegend } from "@/components/charts/chart-legend";
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
    origin: "synthetic",
    text: "One of many paths from a scenario run. In this prototype every number is synthetic.",
  },
];

const NOT_CLAIMED = [
  "That an alternative company history is proven. Scenarios are conditional on stated assumptions.",
  "That an accurate forecast proves the effect of a decision. Prediction and cause are measured separately.",
  "That a p10 to p90 band contains the real outcome 80% of the time, until coverage is measured.",
  "A share price, a fair market value or investment advice.",
];

const PHASES: ReadonlyArray<{ name: string; stages: string; status: string }> = [
  {
    name: "Product and interface foundation",
    stages: "Stages 01 to 08",
    status: "Done on synthetic data",
  },
  {
    name: "Point-in-time data from SEC, FRED, ECB and World Bank",
    stages: "Stages 09 to 14",
    status: "Planned",
  },
  {
    name: "Baselines, temporal neural networks and calibration",
    stages: "Stages 15 to 18",
    status: "Planned",
  },
  {
    name: "Decision registry, causal research, finance and Monte Carlo",
    stages: "Stages 19 to 23",
    status: "Planned",
  },
  { name: "Security, reports and publication", stages: "Stages 24 to 26", status: "Planned" },
];

export default function OverviewPage() {
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
            <ButtonLink href="/methodology">Read the methodology</ButtonLink>
            <ButtonLink href="/decisions" variant="secondary">
              Build a scenario
            </ButtonLink>
          </div>
          <p className="text-small text-ink-muted">
            This prototype runs on fictional companies and fixed mock results; the simulation engine
            arrives in Stage 22. No page on this site uses real company data so far.
          </p>
        </div>
        <figure className="rounded-frame border border-line bg-surface p-4 md:p-6">
          <TimelineMotif />
          <figcaption className="mt-4 flex flex-col gap-3 border-t border-line pt-4">
            <ChartLegend />
            <p className="text-micro text-ink-muted">
              Illustration of the chart language. Not data.
            </p>
          </figcaption>
        </figure>
      </section>

      <Section
        id="trust"
        title="Every result says how far to trust it"
        intro="Each scenario result will open with the same six facts, so a number never travels without its context."
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
        intro="The platform is built in 26 stages. Each one is reviewed before the next begins."
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
                <span className="text-small whitespace-nowrap text-ink-muted tabular-nums">
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
