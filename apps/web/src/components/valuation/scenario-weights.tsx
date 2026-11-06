"use client";

import type { ValuationReport } from "@multiverse/contracts";
import { useId, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { TextField } from "@/components/ui/field";
import { formatValue } from "@/results/format";
import { weightedValue } from "@/valuation/dcf";

/** Weights of the three scenarios: a choice, not a measured probability. */
export function ScenarioWeights({ rows }: { rows: ValuationReport["scenarios"] }) {
  const [texts, setTexts] = useState(() => rows.map((row) => String(Number(row.weight) * 100)));
  const id = useId();
  const weights = texts.map((text) => (text.trim() === "" ? Number.NaN : Number(text) / 100));
  const value = weightedValue(
    rows.map((row) => Number(row.ev_mean)),
    weights,
  );
  return (
    <form className="flex flex-col gap-3" onSubmit={(event) => event.preventDefault()}>
      <div className="grid gap-3 sm:grid-cols-3">
        {rows.map((row, index) => (
          <TextField
            key={row.scenario}
            id={`${id}-${row.scenario}`}
            label={`${row.label} weight, %`}
            type="number"
            step="any"
            value={texts[index] ?? ""}
            onChange={(event) =>
              setTexts((current) =>
                current.map((text, place) => (place === index ? event.target.value : text)),
              )
            }
          />
        ))}
      </div>
      {value === null ? (
        <Alert tone="negative" title="These weights are not a whole" live>
          Scenario weights add up to exactly 100%, and none is negative.
        </Alert>
      ) : (
        <p aria-live="polite" className="text-body text-ink tabular-nums">
          Weighted enterprise value (model): {formatValue(value, "usd")}. The weights are a choice,
          not a measured probability.
        </p>
      )}
    </form>
  );
}
