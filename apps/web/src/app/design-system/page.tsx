import type { ResultMode } from "@multiverse/contracts";
import { Download, Play } from "lucide-react";
import type { Metadata } from "next";
import { ChartLegend } from "@/components/charts/chart-legend";
import { InferenceModeBadge } from "@/components/trust/inference-mode-badge";
import { NotClaims } from "@/components/trust/not-claims";
import { SourceBadge } from "@/components/trust/source-badge";
import { TrustHeader } from "@/components/trust/trust-header";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { CheckboxField, SelectField, TextField } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { LoadingRegion, Skeleton } from "@/components/ui/skeleton";
import { PageHeader, Section } from "@/layouts/page-header";
import { MIN_NON_TEXT_CONTRAST, MIN_TEXT_CONTRAST, contrastRatio } from "@/tokens/contrast";
import { readColorTokens, tokenHex } from "@/tokens/color-tokens";

export const metadata: Metadata = { title: "Design system" };

const ROLES: Record<string, string> = {
  canvas: "Page background",
  surface: "Panels and navigation",
  inset: "Inputs, table headers, hover",
  line: "Decorative separators",
  "line-strong": "Boundaries of controls",
  ink: "Primary text",
  "ink-muted": "Secondary text",
  mint: "Primary action, alternate A, focus",
  "mint-strong": "Primary action hover",
  blue: "Baseline forecast, information",
  violet: "Alternate B",
  observed: "Observed history",
  warning: "Demo and caution states",
  negative: "Errors and destructive actions",
};

const TYPE_SCALE = [
  {
    token: "display",
    size: "60",
    sample: "Financial parallel universes",
    className: "font-display text-display",
  },
  { token: "h1", size: "48", sample: "Company dossier", className: "font-display text-h1" },
  { token: "h2", size: "36", sample: "Scenario comparison", className: "font-display text-h2" },
  { token: "h3", size: "24", sample: "Assumptions", className: "font-display text-h3" },
  { token: "h4", size: "21", sample: "Financing mix", className: "font-display text-h4" },
  {
    token: "lead",
    size: "18",
    sample: "A precise, readable lede for a page.",
    className: "text-lead",
  },
  { token: "body", size: "16", sample: "Body text and form controls.", className: "text-body" },
  {
    token: "small",
    size: "14",
    sample: "Secondary text, tables and hints.",
    className: "text-small",
  },
  { token: "micro", size: "12", sample: "Labels on badges and legends.", className: "text-micro" },
];

const MODES: readonly ResultMode[] = [
  "demo",
  "empirical_forecast",
  "causal_study",
  "fictional_exploratory",
];

interface DemoRow {
  quarter: string;
  revenue: string;
  ebitdaMargin: string;
  fcf: string;
  rnd: string;
}

/* Synthetic numbers for a fictional company; they illustrate the table component only. */
const DEMO_ROWS: readonly DemoRow[] = [
  { quarter: "FY2022 Q1", revenue: "1,204", ebitdaMargin: "21.4%", fcf: "148", rnd: "212" },
  { quarter: "FY2022 Q2", revenue: "1,262", ebitdaMargin: "22.0%", fcf: "171", rnd: "219" },
  { quarter: "FY2022 Q3", revenue: "1,198", ebitdaMargin: "19.8%", fcf: "122", rnd: "—" },
  { quarter: "FY2022 Q4", revenue: "1,311", ebitdaMargin: "23.1%", fcf: "196", rnd: "231" },
];

function ratio(value: number): string {
  return `${value.toFixed(1)}:1`;
}

export default function DesignSystemPage() {
  const tokens = readColorTokens();
  const canvas = tokenHex(tokens, "canvas");
  const surface = tokenHex(tokens, "surface");

  return (
    <>
      <PageHeader
        title="Design system"
        summary="Tokens, components and states of the MULTIVERSE interface. Every example on this page uses synthetic values."
        meta={<InferenceModeBadge mode="demo" />}
      />

      <Section
        id="colour"
        title="Colour"
        intro={`Contrast is computed from the tokens file at build time. Text needs ${MIN_TEXT_CONTRAST}:1, control boundaries ${MIN_NON_TEXT_CONTRAST}:1.`}
      >
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(14rem,1fr))] gap-4">
          {tokens.map((token) => (
            <li key={token.name} className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="size-12 shrink-0 rounded-control border border-line"
                style={{ backgroundColor: token.hex }}
              />
              <div className="flex min-w-0 flex-col text-small">
                <span className="font-medium text-ink">{token.name}</span>
                <span className="text-ink-muted">{ROLES[token.name] ?? "Token"}</span>
                <span className="text-micro text-ink-muted tabular-nums">
                  {token.hex}, {ratio(contrastRatio(token.hex, canvas))} on canvas,{" "}
                  {ratio(contrastRatio(token.hex, surface))} on surface
                </span>
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        id="type"
        title="Typography"
        intro="Space Grotesk for headings and large figures, DM Sans for everything else. All numbers use tabular figures."
      >
        <ul className="flex flex-col divide-y divide-line">
          {TYPE_SCALE.map((step) => (
            <li
              key={step.token}
              className="flex flex-col gap-1 py-3 md:flex-row md:items-baseline md:gap-8"
            >
              <span className="w-28 shrink-0 text-micro text-ink-muted tabular-nums">
                {step.token}, {step.size}px
              </span>
              <span className={`${step.className} min-w-0 text-ink`}>{step.sample}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        id="buttons"
        title="Buttons"
        intro="One primary action per view. Disabled buttons explain why nearby."
      >
        <div className="flex flex-wrap items-center gap-3">
          <Button>
            <Play aria-hidden="true" />
            Run scenario
          </Button>
          <Button variant="secondary">
            <Download aria-hidden="true" />
            Export CSV
          </Button>
          <Button variant="ghost">Reset assumptions</Button>
          <Button variant="danger">Delete scenario</Button>
          <Button disabled>Run scenario</Button>
          <Button size="sm" variant="secondary">
            Small
          </Button>
        </div>
      </Section>

      <Section
        id="forms"
        title="Form fields"
        intro="Labels above controls, units next to values, errors with an icon and text."
      >
        <form className="grid max-w-3xl gap-6 md:grid-cols-2" aria-label="Form field examples">
          <TextField
            id="ds-amount"
            name="amount"
            label="R&D increase"
            unit="% of last year's R&D"
            inputMode="decimal"
            defaultValue="40"
            hint="Share of the previous year's R&D budget, not of revenue."
          />
          <TextField
            id="ds-debt"
            name="debt"
            label="Debt financing"
            unit="%"
            inputMode="decimal"
            defaultValue="95"
            required
            error="Cash, debt and equity add up to 95%. They must add up to 100%."
          />
          <SelectField id="ds-type" name="type" label="Decision type" defaultValue="rnd">
            <option value="rnd">R&D change</option>
            <option value="workforce">Workforce restructuring</option>
            <option value="acquisition">Acquisition</option>
            <option value="divestiture">Divestiture</option>
            <option value="capex">CAPEX expansion</option>
            <option value="refinance">Debt refinancing</option>
          </SelectField>
          <TextField
            id="ds-disabled"
            name="model"
            label="Model"
            defaultValue="Not available in demo mode"
            disabled
          />
          <div className="md:col-span-2">
            <CheckboxField
              id="ds-seed"
              name="seed"
              label="Lock random seed"
              hint="Same seed, same configuration and same model give identical results."
              defaultChecked
            />
          </div>
        </form>
      </Section>

      <Section
        id="badges"
        title="Status and provenance"
        intro="Badges carry text and an icon; colour only supports the meaning."
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {MODES.map((mode) => (
              <InferenceModeBadge key={mode} mode={mode} />
            ))}
          </div>
          <div className="flex flex-wrap gap-4">
            <SourceBadge kind="observed" origin="empirical" />
            <SourceBadge kind="forecast" origin="empirical" />
            <SourceBadge kind="simulated" origin="synthetic" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge>Neutral</Badge>
            <Badge tone="blue">Planned for Stage 05</Badge>
            <Badge tone="negative">Stale, requires rerun</Badge>
          </div>
        </div>
      </Section>

      <Section id="alerts" title="Alerts">
        <div className="grid max-w-3xl gap-3">
          <Alert tone="info" title="Partial coverage">
            R&D expense is missing for 3 of 20 quarters. Missing values are shown as missing, never
            as zero.
          </Alert>
          <Alert tone="success" title="Scenario saved on this device">
            Revision 3 of the R&D study is stored in this browser only.
          </Alert>
          <Alert tone="warning" title="Out of the training range">
            An R&D increase of 120% is larger than any observed case. The result would be
            extrapolation.
          </Alert>
          <Alert tone="negative" title="Run failed">
            The worker stopped (incident demo-17). Retrying reuses the same request and creates no
            duplicate.
          </Alert>
        </div>
      </Section>

      <Section id="trust" title="Result header">
        <div className="flex flex-col gap-4">
          <TrustHeader
            mode="demo"
            evidence="Synthetic fixture, no sources"
            asOf="2022-12-31"
            model="None, demo formulas"
            uncertainty="conditional_model_quantiles"
            calibrated={false}
            auditId="demo-0001"
          />
          <NotClaims
            items={[
              "Not a forecast of the real company: the data is synthetic.",
              "The band is not a probability of the real outcome; it is not calibrated.",
              "No causal effect of the decision is estimated here.",
            ]}
          />
        </div>
      </Section>

      <Section
        id="table"
        title="Table"
        intro="Scrolls with the keyboard, keeps headers in view, and turns into cards when it is narrower than 600px."
      >
        <DataTable<DemoRow>
          id="demo-financials"
          caption={
            <span className="flex flex-wrap items-center gap-2">
              Northwind Semiconductors (fictional), quarterly results in USD m
              <SourceBadge kind="observed" origin="synthetic" />
            </span>
          }
          rowKey={(row) => row.quarter}
          rows={DEMO_ROWS}
          columns={[
            { key: "quarter", header: "Fiscal quarter", rowHeader: true },
            { key: "revenue", header: "Revenue", numeric: true },
            { key: "ebitdaMargin", header: "EBITDA margin (calculated)", numeric: true },
            { key: "fcf", header: "FCF (CFO − CAPEX)", numeric: true },
            { key: "rnd", header: "R&D expense", numeric: true },
          ]}
        />
        <p className="mt-2 text-micro text-ink-muted">
          A dash marks a value that is missing, here R&D for FY2022 Q3.
        </p>
      </Section>

      <Section id="loading" title="Loading">
        <LoadingRegion label="Loading company data" className="grid max-w-3xl gap-3">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-6 w-2/3" />
        </LoadingRegion>
      </Section>

      <Section
        id="dialog"
        title="Dialog"
        intro="A native modal dialog: Esc closes it and focus returns to the button that opened it."
      >
        <Modal
          title="Discard changes to this scenario?"
          description="Revision 3 has unsaved assumptions. Discarding keeps revision 2 as it was."
          triggerLabel="Open example dialog"
          cancelLabel="Keep editing"
          confirmLabel="Discard changes"
        />
      </Section>

      <Section
        id="charts"
        title="Chart grammar"
        intro="Series differ by line style as well as colour, so they stay distinguishable without colour vision."
      >
        <ChartLegend />
      </Section>
    </>
  );
}
