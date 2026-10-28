"use client";

import type { Distribution } from "@multiverse/contracts/interventions";
import { CONTROL, describedBy, FieldMessage, FieldShell } from "@/components/ui/field";
import type { DistributionField } from "@/decisions/form";
import { cn } from "@/lib/cn";

/*
 * Reusable decision inputs (PRD FR-DE-03). Numbers are typed as text with
 * inputmode="decimal": a type="number" field changes on scroll and hides what was typed.
 * Every slider has a numeric field next to it, the unit is always visible, and the
 * slider's aria-valuetext reads the value with its unit.
 */

export interface SliderRange {
  min: number;
  max: number;
  step: number;
}

interface NumberFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Visible unit after the value, e.g. "%" or "USD m". */
  unit: string;
  /** The value with its full unit for assistive technology, e.g. "40 percent of revenue". */
  valueText?: string;
  hint?: string;
  error?: string | undefined;
  warning?: string | undefined;
  slider?: SliderRange | undefined;
  required?: boolean;
}

function UnitInput({
  id,
  value,
  onChange,
  unit,
  invalid,
  describedById,
  name,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  unit: string;
  invalid: boolean;
  describedById: string | undefined;
  name?: string;
}) {
  return (
    <div className="flex items-stretch">
      <input
        id={id}
        name={name ?? id}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedById}
        className={cn(CONTROL, "min-w-0 rounded-r-none tabular-nums")}
      />
      <span
        className="flex shrink-0 items-center rounded-r-control border border-l-0 border-line-strong bg-surface px-3 text-small text-ink-muted"
        aria-hidden="true"
      >
        {unit}
      </span>
    </div>
  );
}

export function NumberField({
  id,
  label,
  value,
  onChange,
  unit,
  valueText,
  hint,
  error,
  warning,
  slider,
  required,
}: NumberFieldProps) {
  const described = describedBy(id, hint, error, warning);
  const numeric = Number(value);
  const sliderValue = slider
    ? Math.min(slider.max, Math.max(slider.min, Number.isFinite(numeric) ? numeric : slider.min))
    : 0;
  return (
    <FieldShell
      id={id}
      label={label}
      hint={hint}
      error={error}
      warning={warning}
      required={required}
    >
      <UnitInput
        id={id}
        value={value}
        onChange={onChange}
        unit={unit}
        invalid={Boolean(error)}
        describedById={described}
      />
      {slider ? (
        <input
          type="range"
          aria-label={`${label}, slider`}
          aria-valuetext={valueText ?? `${value} ${unit}`}
          aria-describedby={described}
          min={slider.min}
          max={slider.max}
          step={slider.step}
          value={sliderValue}
          onChange={(event) => onChange(event.target.value)}
          className="decision-slider"
        />
      ) : null}
    </FieldShell>
  );
}

const SHAPE_LABELS: Record<Distribution["shape"], string> = {
  fixed: "Fixed value",
  uniform: "Uniform range",
  triangular: "Triangular range",
};

const POINT_LABELS = { value: "Value", low: "Low", mode: "Most likely", high: "High" } as const;
const SHAPE_POINTS: Record<Distribution["shape"], readonly (keyof typeof POINT_LABELS)[]> = {
  fixed: ["value"],
  uniform: ["low", "high"],
  triangular: ["low", "mode", "high"],
};

interface DistributionInputProps {
  id: string;
  label: string;
  hint: string;
  unit: string;
  field: DistributionField;
  onChange: (field: DistributionField) => void;
  /** Group-level issues (ordering) and point-level errors keyed by point name. */
  error?: string | undefined;
  warning?: string | undefined;
  pointErrors: Partial<Record<keyof typeof POINT_LABELS, string>>;
}

/** An uncertain parameter: a fixed value or a range with a shape (docs/08). */
export function DistributionInput({
  id,
  label,
  hint,
  unit,
  field,
  onChange,
  error,
  warning,
  pointErrors,
}: DistributionInputProps) {
  const groupDescribed = describedBy(id, hint, error, warning);
  return (
    <fieldset id={id} aria-describedby={groupDescribed} className="flex min-w-0 flex-col gap-3">
      <legend className="text-small font-medium text-ink">{label}</legend>
      <p id={`${id}-hint`} className="-mt-1 text-small text-ink-muted">
        {hint}
      </p>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,12rem)_1fr]">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-shape`} className="text-small text-ink-muted">
            Shape
          </label>
          <select
            id={`${id}-shape`}
            value={field.shape}
            onChange={(event) =>
              onChange({ ...field, shape: event.target.value as Distribution["shape"] })
            }
            className={cn(CONTROL, "appearance-auto")}
          >
            {Object.entries(SHAPE_LABELS).map(([shape, text]) => (
              <option key={shape} value={shape}>
                {text}
              </option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-1 gap-3 min-[30rem]:grid-cols-3">
          {SHAPE_POINTS[field.shape].map((point) => {
            const pointId = `${id}-${point}`;
            const pointError = pointErrors[point];
            return (
              <div key={point} className="flex min-w-0 flex-col gap-1.5">
                <label htmlFor={pointId} className="text-small text-ink-muted">
                  {POINT_LABELS[point]}
                </label>
                <UnitInput
                  id={pointId}
                  value={field[point]}
                  onChange={(value) => onChange({ ...field, [point]: value })}
                  unit={unit}
                  invalid={Boolean(pointError)}
                  describedById={pointError ? `${pointId}-error` : undefined}
                />
                {pointError ? (
                  <FieldMessage id={`${pointId}-error`} tone="error">
                    {pointError}
                  </FieldMessage>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
      {error ? (
        <FieldMessage id={`${id}-error`} tone="error">
          {error}
        </FieldMessage>
      ) : null}
      {warning ? (
        <FieldMessage id={`${id}-warning`} tone="warning">
          {warning}
        </FieldMessage>
      ) : null}
    </fieldset>
  );
}

interface SharesInputProps {
  id: string;
  label: string;
  explanation: string;
  members: readonly { key: string; label: string }[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  /** Live total, e.g. "95%", or null while a share cannot be read. */
  total: string | null;
  complete: boolean;
  error?: string | undefined;
  warning?: string | undefined;
  memberErrors: Record<string, string | undefined>;
}

/** Shares that must add up to 100%. The total is shown live and never normalized. */
export function SharesInput({
  id,
  label,
  explanation,
  members,
  values,
  onChange,
  total,
  complete,
  error,
  warning,
  memberErrors,
}: SharesInputProps) {
  return (
    <fieldset
      id={id}
      aria-describedby={describedBy(id, explanation, error, warning)}
      className="flex min-w-0 flex-col gap-3"
    >
      <legend className="text-small font-medium text-ink">{label}</legend>
      <p id={`${id}-hint`} className="-mt-1 text-small text-ink-muted">
        {explanation}
      </p>
      <div className="grid grid-cols-1 gap-3 min-[30rem]:grid-cols-3">
        {members.map((member) => {
          const memberId = `${id}-${member.key.replaceAll("_", "-")}`;
          const memberError = memberErrors[member.key];
          return (
            <div key={member.key} className="flex min-w-0 flex-col gap-1.5">
              <label htmlFor={memberId} className="text-small text-ink-muted">
                {member.label}
              </label>
              <UnitInput
                id={memberId}
                value={values[member.key] ?? ""}
                onChange={(value) => onChange(member.key, value)}
                unit="%"
                invalid={Boolean(memberError)}
                describedById={memberError ? `${memberId}-error` : `${id}-total`}
              />
              {memberError ? (
                <FieldMessage id={`${memberId}-error`} tone="error">
                  {memberError}
                </FieldMessage>
              ) : null}
            </div>
          );
        })}
      </div>
      <output
        id={`${id}-total`}
        aria-live="polite"
        className={cn("text-small", complete ? "text-mint" : "text-ink-muted")}
      >
        {total === null
          ? "Total: enter every share to see it."
          : complete
            ? `Total ${total}.`
            : `Total ${total}. It must be exactly 100%.`}
      </output>
      {error ? (
        <FieldMessage id={`${id}-error`} tone="error">
          {error}
        </FieldMessage>
      ) : null}
      {warning ? (
        <FieldMessage id={`${id}-warning`} tone="warning">
          {warning}
        </FieldMessage>
      ) : null}
    </fieldset>
  );
}
