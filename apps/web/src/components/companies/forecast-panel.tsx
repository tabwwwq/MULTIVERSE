import type { CompanyDossier, RealCompany } from "@multiverse/contracts";
import { ForecastChart } from "@/components/companies/forecast-chart";
import { Alert } from "@/components/ui/alert";
import { type Column, DataTable } from "@/components/ui/data-table";

type Forecast = NonNullable<RealCompany["forecast"]>;
type Band = Forecast["bands"][number];

/** Columns of the seven levels: 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95. */
const P10 = 1;
const P50 = 3;
const P90 = 5;
const SHOWN = [1, 4, 8];

const TARGETS: Record<Band["target"], string> = {
  revenue_growth: "Revenue growth over a year",
  operating_margin: "Operating margin",
  ebitda_margin: "EBITDA margin",
  fcf_margin: "FCF margin",
  debt_to_ebitda: "Debt / EBITDA",
};

function shown(band: Band, level: number): string {
  const value = band.values[level] ?? Number.NaN;
  return band.target === "debt_to_ebitda" ? `${value.toFixed(1)}×` : `${(100 * value).toFixed(1)}%`;
}

function quarter(day: string): string {
  const month = Number(day.slice(5, 7));
  return `${day.slice(0, 4)} Q${Math.ceil(month / 3)}`;
}

interface Row {
  id: string;
  target: string;
  quarter: string;
  p10: string;
  p50: string;
  p90: string;
}

const COLUMNS: ReadonlyArray<Column<Row>> = [
  { key: "target", header: "Measure", rowHeader: true, render: (row) => row.target },
  { key: "quarter", header: "Quarter", render: (row) => row.quarter },
  { key: "p10", header: "p10", numeric: true, render: (row) => row.p10 },
  { key: "p50", header: "p50", numeric: true, render: (row) => row.p50 },
  { key: "p90", header: "p90", numeric: true, render: (row) => row.p90 },
];

interface ForecastPanelProps {
  dossier: CompanyDossier;
  forecast: Forecast;
  id: string | null;
}

export function ForecastPanel({ dossier, forecast, id }: ForecastPanelProps) {
  const rows = forecast.bands
    .filter((band) => SHOWN.includes(band.horizon))
    .map((band) => ({
      id: `${band.target}-${band.horizon}`,
      target: TARGETS[band.target],
      quarter: quarter(band.quarter_end),
      p10: shown(band, P10),
      p50: shown(band, P50),
      p90: shown(band, P90),
    }));
  return (
    <div className="flex flex-col gap-4">
      <Alert tone="warning" title="Research forecast, not approved for the product">
        A temporal network trained on SEC filings of 1,429 companies and on Treasury and ECB rates.
        It does not know about any decision. p10 to p90 is its stated range: on the years 2024 to
        2026 such ranges held 82% of outcomes for revenue growth over 4 quarters and 85% for EBITDA
        margin, against 80% stated. That is past years, not a promise for these. This is not advice.
      </Alert>
      <ForecastChart dossier={dossier} forecast={forecast} />
      <DataTable
        id="forecast"
        columns={COLUMNS}
        rows={rows}
        rowKey={(row) => row.id}
        caption={`Model forecast ${id ?? ""}`}
      />
      <p className="text-small text-ink-muted">
        Inputs: SEC filings and U.S. Treasury yields. Source: ECB statistics. None of them has
        reviewed or endorsed this forecast.
      </p>
    </div>
  );
}
