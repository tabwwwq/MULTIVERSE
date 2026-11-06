/**
 * The valuation and risk studio of the research case (Stage 23). The JSON is written by
 * `python -m multiverse_simulation studio` and validated by the Python contracts in CI.
 */
import type { ValuationReport } from "./generated/contracts";
import data from "../../../../data/valuation/report-48898.json";

// JSON imports widen literal types; the Python contracts validate the file in CI.
export const VALUATION_REPORT: ValuationReport = data as unknown as ValuationReport;
