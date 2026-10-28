import type { InterventionSpec } from "@multiverse/contracts";
import type { DecisionType } from "@multiverse/contracts/interventions";
import { CATALOG } from "@/decisions/catalog";
import { cn } from "@/lib/cn";

const STATEMENT_LABELS = {
  income_statement: "Income statement",
  cash_flow: "Cash flow",
  balance_sheet: "Balance sheet",
} as const;

/** Which statements a decision touches and what it does not mean (PRD FR-DE-08). */
export function MechanismPanel({
  spec,
  className,
}: {
  spec: InterventionSpec;
  className?: string;
}) {
  return (
    <section
      aria-label={`How ${spec.label.toLowerCase()} works`}
      className={cn(
        "flex flex-col gap-4 rounded-panel border border-line bg-surface p-4 md:p-5",
        className,
      )}
    >
      <div>
        <p className="text-small text-ink-muted">How it works</p>
        <p className="font-display text-h4 text-ink">{spec.label}</p>
      </div>
      <dl className="flex flex-col gap-3">
        {spec.mechanism.map((effect) => (
          <div key={effect.statement} className="flex flex-col gap-0.5">
            <dt className="text-small font-medium text-ink">
              {STATEMENT_LABELS[effect.statement]}
            </dt>
            <dd className="text-small text-ink-muted">{effect.effect}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-col gap-0.5 border-t border-line pt-3">
        <p className="text-small font-medium text-ink">What this does not mean</p>
        <p className="text-small text-ink-muted">{spec.does_not_mean}</p>
      </div>
      <div className="flex flex-col gap-0.5 border-t border-line pt-3">
        <p className="text-small font-medium text-ink">Evidence</p>
        <p className="text-small text-ink-muted">{spec.evidence}</p>
      </div>
    </section>
  );
}

interface TypePickerProps {
  value: DecisionType;
  onChange: (type: DecisionType) => void;
}

/** Six decision types as radio cards: all choices visible, each with its summary. */
export function DecisionTypePicker({ value, onChange }: TypePickerProps) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-3">
      <legend className="sr-only">Decision type</legend>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {CATALOG.interventions.map((spec) => {
          const id = `type-${spec.type}`;
          return (
            <label
              key={spec.type}
              htmlFor={id}
              className="flex min-h-12 cursor-pointer items-start gap-3 rounded-panel border border-line-strong bg-surface p-4 has-checked:border-mint has-checked:bg-inset has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-mint"
            >
              <input
                id={id}
                type="radio"
                name="decision-type"
                value={spec.type}
                checked={value === spec.type}
                onChange={() => onChange(spec.type)}
                className="mt-1 size-5 shrink-0 accent-mint"
              />
              <span className="flex flex-col gap-0.5">
                <span className="font-medium text-ink">{spec.label}</span>
                <span className="text-small text-ink-muted">{spec.summary}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
