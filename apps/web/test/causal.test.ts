import { CAUSAL_STUDY } from "@multiverse/contracts/causal";
import { describe, expect, it } from "vitest";
import { METHOD_LABELS, POSITIONS, feasibleCount, growthRow } from "../src/causal/study";

describe("causal study", () => {
  it("claims no effect", () => {
    expect(CAUSAL_STUDY.effects_estimated).toBe(0);
    expect(CAUSAL_STUDY.outcomes_after_treatment_read).toBe(false);
    expect(CAUSAL_STUDY.label).toBe("feasibility_study_no_effect_estimated");
  });

  it("draws every node of the graph", () => {
    for (const node of CAUSAL_STUDY.graph.nodes) expect(POSITIONS[node.node_id]).toBeDefined();
  });

  it("says why every closed method is closed", () => {
    for (const row of CAUSAL_STUDY.treatments) {
      expect(feasibleCount(row)).toBe(0);
      for (const verdict of row.verdicts) {
        expect(METHOD_LABELS[verdict.method]).toBeTruthy();
        expect(verdict.reasons.length).toBeGreaterThan(0);
      }
    }
  });

  it("reads the growth row of the null", () => {
    const first = CAUSAL_STUDY.treatments[0];
    if (!first) throw new Error("no treatments");
    expect(growthRow(first)?.outcome).toBe("rev_growth_l1");
    expect(growthRow({ ...first, null: [] })).toBeUndefined();
  });
});
