/**
 * The causal feasibility study (Stage 20). The JSON is written by `python -m multiverse_causal`
 * and validated by the Python contracts in CI. It holds diagnostics, never an effect.
 */
import type { CausalStudy } from "./generated/contracts";
import data from "../../../../data/causal/study.json";

export type TreatmentStudy = CausalStudy["treatments"][number];

// JSON imports widen literal types; the Python contracts validate the file in CI.
export const CAUSAL_STUDY: CausalStudy = data as unknown as CausalStudy;
