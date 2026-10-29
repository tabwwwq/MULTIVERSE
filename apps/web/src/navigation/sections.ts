import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpenText,
  Building2,
  Calculator,
  ChartSpline,
  Columns2,
  Cpu,
  Database,
  FileText,
  GitBranchPlus,
  History,
  Network,
  NotebookPen,
  Orbit,
  Rocket,
  ScanSearch,
  Search,
  Settings,
  ShieldAlert,
  SlidersHorizontal,
} from "lucide-react";

/**
 * The 20 screens of the information architecture (docs/02_USER_EXPERIENCE.md).
 * `available` sections have a real page; `planned` ones render an honest placeholder
 * that names the stage which builds them. Navigation, breadcrumbs, the placeholder
 * route and the tests all read this list.
 */

export type SectionStatus = "available" | "planned";

export interface NavGroup {
  id: string;
  label: string;
}

export interface Section {
  slug: string;
  href: string;
  title: string;
  group: NavGroup["id"];
  icon: LucideIcon;
  summary: string;
  status: SectionStatus;
  /** Stage that delivers the section (prompts/NN_*.md). */
  stage: number;
  stageName: string;
  /** What the finished section will do, shown on the placeholder page. */
  plans: readonly string[];
}

export const NAV_GROUPS: readonly NavGroup[] = [
  { id: "overview", label: "Overview" },
  { id: "explore", label: "Explore" },
  { id: "build", label: "Build a scenario" },
  { id: "analyse", label: "Analyse" },
  { id: "record", label: "Record" },
  { id: "platform", label: "Platform" },
];

export const SECTIONS: readonly Section[] = [
  {
    slug: "",
    href: "/",
    title: "Overview",
    group: "overview",
    icon: Orbit,
    summary: "What MULTIVERSE is, what it will not claim, and how far the build has come.",
    status: "available",
    stage: 3,
    stageName: "Design system and shell",
    plans: [],
  },
  {
    slug: "methodology",
    href: "/methodology",
    title: "Methodology",
    group: "overview",
    icon: BookOpenText,
    summary: "Inference levels, result modes, uncertainty, point-in-time data and limitations.",
    status: "available",
    stage: 3,
    stageName: "Design system and shell",
    plans: [],
  },
  {
    slug: "universe",
    href: "/universe",
    title: "Universe Explorer",
    group: "explore",
    icon: Search,
    summary: "Find a company by ticker, name or CIK and see its data coverage.",
    status: "available",
    stage: 4,
    stageName: "Company Explorer and dossier",
    plans: [
      "Search by ticker, company name or CIK, including former tickers.",
      "Sector, country and lifecycle filters.",
      "Coverage and data quality for every company, with missing data shown as missing.",
    ],
  },
  {
    slug: "dossier",
    href: "/dossier",
    title: "Company Dossier",
    group: "explore",
    icon: Building2,
    summary:
      "Revenue, margins, cash flow and debt history with the original filings behind each value.",
    status: "available",
    stage: 4,
    stageName: "Company Explorer and dossier",
    plans: [
      "Revenue, EBITDA (calculated), FCF and debt history by fiscal quarter.",
      "A link to the original filing for every value.",
      "Fiscal calendar, reporting currency and data quality flags.",
    ],
  },
  {
    slug: "time-machine",
    href: "/time-machine",
    title: "Time Machine",
    group: "explore",
    icon: History,
    summary: "Compare what was public about companies at different historical cutoffs.",
    status: "planned",
    stage: 12,
    stageName: "Point-in-time warehouse",
    plans: [
      "Compare two cutoffs side by side and see which values became public in between.",
      "Original, vintage and latest views of values that were later restated.",
      "Coverage per cutoff for the whole universe. A single-company cutoff already exists in the Company Dossier.",
    ],
  },
  {
    slug: "decisions",
    href: "/decisions",
    title: "Decision Builder",
    group: "build",
    icon: GitBranchPlus,
    summary: "Define a management decision with its size, unit, timing, cost and financing.",
    status: "available",
    stage: 5,
    stageName: "Decision Builder",
    plans: [
      "Six decision types: R&D, workforce restructuring, acquisition, divestiture, CAPEX and refinancing.",
      "Every amount has an explicit unit, so +40% of budget is never confused with +40 percentage points.",
      "Validation of ranges and financing mix before anything runs.",
    ],
  },
  {
    slug: "assumptions",
    href: "/assumptions",
    title: "Assumption Matrix",
    group: "build",
    icon: SlidersHorizontal,
    summary:
      "Every parameter of every decision type, with its unit, ranges, default and the source of that default.",
    status: "available",
    stage: 5,
    stageName: "Decision Builder",
    plans: [
      "Controllable parameters with allowed and planning ranges.",
      "The source of every default value.",
      "Locking parameters for paired comparisons arrives with the Monte Carlo engine (Stage 22).",
    ],
  },
  {
    slug: "launch",
    href: "/launch",
    title: "Launch Center",
    group: "build",
    icon: Rocket,
    summary: "Check data readiness, model version and run cost before starting a scenario.",
    status: "planned",
    stage: 22,
    stageName: "Monte Carlo engine",
    plans: [
      "Data readiness and model version check.",
      "Run size and cost estimate before anything starts.",
      "Fixed seed for reproducible runs.",
    ],
  },
  {
    slug: "monitor",
    href: "/monitor",
    title: "Simulation Monitor",
    group: "build",
    icon: Activity,
    summary: "Follow long-running jobs: queued, running, paused, stopped, failed or completed.",
    status: "planned",
    stage: 18,
    stageName: "Training operations",
    plans: [
      "Live job status with last heartbeat.",
      "Stop after checkpoint, and resume.",
      "Jobs keep running when the browser is closed.",
    ],
  },
  {
    slug: "timeline",
    href: "/timeline",
    title: "Timeline Explorer",
    group: "analyse",
    icon: ChartSpline,
    summary: "Baseline and alternative paths with quantile bands and decision markers.",
    status: "available",
    stage: 6,
    stageName: "Timeline charts and comparison",
    plans: [
      "Observed history, baseline forecast and alternatives in one chart.",
      "p10, p50 and p90 bands labelled with what they mean.",
      "Every chart also available as a table and CSV.",
    ],
  },
  {
    slug: "compare",
    href: "/compare",
    title: "Universe Compare",
    group: "analyse",
    icon: Columns2,
    summary: "Side-by-side comparison of scenarios with paired differences.",
    status: "available",
    stage: 6,
    stageName: "Timeline charts and comparison",
    plans: [
      "Side-by-side KPIs and waterfalls.",
      "Distribution of differences against the paired baseline.",
      "Blocks comparisons with different currencies, horizons or cutoffs.",
    ],
  },
  {
    slug: "risk",
    href: "/risk",
    title: "Risk Observatory",
    group: "analyse",
    icon: ShieldAlert,
    summary: "Downside, leverage, liquidity and tail risks of a scenario.",
    status: "planned",
    stage: 23,
    stageName: "Valuation and risk studio",
    plans: [
      "Probability of cash shortfall and covenant breach, under the assumed model.",
      "Top adverse combinations of drivers.",
      "Stress tests on rates, revenue and margins.",
    ],
  },
  {
    slug: "valuation",
    href: "/valuation",
    title: "Valuation Studio",
    group: "analyse",
    icon: Calculator,
    summary:
      "DCF on free cash flow to the firm, with enterprise value and equity value kept apart.",
    status: "planned",
    stage: 23,
    stageName: "Valuation and risk studio",
    plans: [
      "Discounted cash flow with a visible WACC breakdown.",
      "Enterprise value and equity value as separate results, with the bridge between them.",
      "Sensitivity of value to WACC and terminal growth.",
    ],
  },
  {
    slug: "causal-map",
    href: "/causal-map",
    title: "Causal Map",
    group: "analyse",
    icon: Network,
    summary: "The assumed cause-and-effect graph, with confounders and untested assumptions.",
    status: "planned",
    stage: 20,
    stageName: "Causal research pipeline",
    plans: [
      "Hypothesised graph of macro conditions, firm state, decision and outcomes.",
      "Confounders and mediators with the reasoning behind them.",
      "Which assumptions are tested and which are not.",
    ],
  },
  {
    slug: "explainability",
    href: "/explainability",
    title: "Explainability Room",
    group: "analyse",
    icon: ScanSearch,
    summary: "What drives a forecast, labelled as predictive sensitivity rather than cause.",
    status: "planned",
    stage: 17,
    stageName: "Probabilistic validation",
    plans: [
      "Feature sensitivity and changes against the baseline.",
      "Ablations and nearest historical analogues.",
      "Clear separation between predictive drivers and causal claims.",
    ],
  },
  {
    slug: "notebook",
    href: "/notebook",
    title: "Research Notebook",
    group: "record",
    icon: NotebookPen,
    summary: "Saved scenarios with names, tags, notes and revision history.",
    status: "available",
    stage: 7,
    stageName: "Experiment library",
    plans: [
      "Save, tag and search scenarios.",
      "Every change creates a new revision; exported revisions never change.",
      "Stored only on this device until server storage exists.",
    ],
  },
  {
    slug: "reports",
    href: "/reports",
    title: "Report Studio",
    group: "record",
    icon: FileText,
    summary: "Reproducible reports with sources, versions and limitations.",
    status: "planned",
    stage: 25,
    stageName: "Reports and portfolio",
    plans: [
      "Markdown, CSV and PDF exports.",
      "A reproducibility manifest with data, model and code versions.",
      "Limitations printed next to every result.",
    ],
  },
  {
    slug: "models",
    href: "/models",
    title: "Model Observatory",
    group: "platform",
    icon: Cpu,
    summary: "Training runs, dataset versions, measured metrics and approved models.",
    status: "planned",
    stage: 18,
    stageName: "Training operations",
    plans: [
      "Training runs with their dataset version, seed and configuration.",
      "Metrics from real runs only.",
      "Model approval and rollback.",
    ],
  },
  {
    slug: "data-catalog",
    href: "/data-catalog",
    title: "Data Catalog",
    group: "platform",
    icon: Database,
    summary: "Official sources with their terms, keys, request limits and data dictionaries.",
    status: "available",
    stage: 9,
    stageName: "Source policy and data catalog",
    plans: [
      "Official sources with their licences and access rules.",
      "Coverage and missingness by company, metric and period (Stage 11).",
      "Lineage from the original filing to every number (Stage 11).",
    ],
  },
  {
    slug: "settings",
    href: "/settings",
    title: "Settings & Privacy",
    group: "platform",
    icon: Settings,
    summary: "The data stored on this device, and how to delete all of it.",
    status: "available",
    stage: 7,
    stageName: "Experiment library",
    plans: [
      "List of everything stored on this device.",
      "Delete everything stored on this device.",
      "Display scale and number format settings are in the backlog (FR-ST-01).",
    ],
  },
];

export function sectionByHref(href: string): Section | undefined {
  return SECTIONS.find((section) => section.href === href);
}

export function groupLabel(groupId: string): string {
  return NAV_GROUPS.find((group) => group.id === groupId)?.label ?? groupId;
}

export function formatStage(stage: number): string {
  return `Stage ${String(stage).padStart(2, "0")}`;
}
