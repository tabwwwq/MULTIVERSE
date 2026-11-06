/**
 * The first Monte Carlo run on a real company (Stage 22). The JSON is written by
 * `python -m multiverse_simulation run` and validated by the Python contracts in CI.
 */
import type { SimulationReport } from "./generated/contracts";
import data from "../../../../data/simulation/report-48898-acquisition.json";

// JSON imports widen literal types; the Python contracts validate the file in CI.
export const SIMULATION_REPORT: SimulationReport = data as unknown as SimulationReport;
