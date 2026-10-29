"use client";

import type {
  InterventionSpec,
  MagnitudeUnit,
  MagnitudeUnitSpec,
  ParameterSpec,
} from "@multiverse/contracts";
import type { DecisionType } from "@multiverse/contracts/interventions";
import { RotateCcw } from "lucide-react";
import { useId, useMemo, useRef, useState } from "react";
import {
  DistributionInput,
  NumberField,
  type SliderRange,
  SharesInput,
} from "@/components/decisions/decision-fields";
import { DecisionTypePicker, MechanismPanel } from "@/components/decisions/decision-info";
import { RunDialog } from "@/components/decisions/run-dialog";
import { type SavedTarget, SaveToNotebook } from "@/components/notebook/save-to-notebook";
import { ValidationPanel } from "@/components/decisions/validation-panel";
import { Button } from "@/components/ui/button";
import { CheckboxField, SelectField, TextField } from "@/components/ui/field";
import { CATALOG, specFor, unitSpecFor } from "@/decisions/catalog";
import type { CompanyContext } from "@/decisions/context";
import { fieldId, issuesByPath } from "@/decisions/fields";
import {
  type DecisionForm,
  defaultDecisionForm,
  type DistributionField,
  moveDefaultDates,
  type ScenarioForm,
} from "@/decisions/form";
import { DISPLAY_UNITS, formatValue, toInput } from "@/decisions/units";
import { freshness, type ValidationResult, validateScenario } from "@/decisions/validate";
import { add, parseUserDecimal, toDecimalString } from "@/lib/decimal";

const SOURCE_LABELS = {
  accounting_rule: "accounting rule",
  statutory_rate: "statutory rate",
  design_default: "design default",
  placeholder: "placeholder, not an estimate",
} as const;

function sliderFor(
  spec: { allowed: { min: string; max: string }; step: string },
  unit: ParameterSpec["unit"],
): SliderRange | undefined {
  if (unit === "usd") return undefined;
  return {
    min: Number(toInput(spec.allowed.min, unit)),
    max: Number(toInput(spec.allowed.max, unit)),
    step: Number(toInput(spec.step, unit)),
  };
}

function defaultText(parameter: ParameterSpec): string {
  const value = parameter.default;
  const shown =
    typeof value === "string"
      ? formatValue(value, parameter.unit)
      : value.shape === "fixed"
        ? formatValue(value.value, parameter.unit)
        : value.shape === "uniform"
          ? `${formatValue(value.low, parameter.unit)} to ${formatValue(value.high, parameter.unit)}`
          : `${formatValue(value.low, parameter.unit)} to ${formatValue(value.high, parameter.unit)}, most likely ${formatValue(value.mode, parameter.unit)}`;
  return `Default: ${shown} (${SOURCE_LABELS[parameter.default_source.kind]}).`;
}

/** How to type the size: the unit in words, and whether a negative number is allowed. */
function magnitudeHint(unit: MagnitudeUnitSpec): string {
  const typed =
    unit.value_unit === "usd"
      ? "In millions of US dollars: 1000 means USD 1bn."
      : unit.value_unit === "fraction"
        ? `In percent ${unit.label.replace(/^% /, "")}.`
        : `In ${unit.label}.`;
  return Number(unit.allowed.min) < 0 ? `${typed} Negative values are cuts.` : typed;
}

function shareTotal(values: Record<string, string>, keys: readonly string[]): string | null {
  let total = "0";
  for (const key of keys) {
    const parsed = parseUserDecimal(values[key] ?? "");
    if (parsed === null) return null;
    total = toDecimalString(add(total, parsed));
  }
  return total;
}

/** A saved revision opened in the builder ("restore form", Stage 07). */
export interface RestoredRevision extends SavedTarget {
  form: ScenarioForm;
}

interface DecisionBuilderProps {
  context: CompanyContext;
  initialAsOf: string;
  initialType: DecisionType;
  restored?: RestoredRevision | undefined;
}

export function DecisionBuilder({
  context,
  initialAsOf,
  initialType,
  restored,
}: DecisionBuilderProps) {
  const [asOf, setAsOf] = useState(restored?.form.as_of ?? initialAsOf);
  const [horizon, setHorizon] = useState(
    restored?.form.horizon_quarters ?? String(CATALOG.horizon_quarters.default),
  );
  const [type, setType] = useState<DecisionType>(restored?.form.decision.type ?? initialType);
  const [forms, setForms] = useState<Partial<Record<DecisionType, DecisionForm>>>(
    restored ? { [restored.form.decision.type]: restored.form.decision } : {},
  );
  const [seed] = useState(restored?.form.seed ?? CATALOG.default_seed);
  const [saved, setSaved] = useState<SavedTarget | null>(
    restored
      ? { scenarioId: restored.scenarioId, revision: restored.revision, name: restored.name }
      : null,
  );
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const [announcement, setAnnouncement] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const formId = useId();

  const spec: InterventionSpec = specFor(type);
  const decision = forms[type] ?? defaultDecisionForm(type, asOf);
  const scenario: ScenarioForm = useMemo(
    () => ({
      contracts_version: CATALOG.contracts_version,
      company_id: context.companyId,
      as_of: asOf,
      data_origin: context.dataOrigin,
      horizon_quarters: horizon,
      seed,
      decision,
    }),
    [asOf, context, decision, horizon, seed],
  );
  const state = result ? freshness(result, scenario) : null;
  const visible = useMemo(
    () =>
      result
        ? issuesByPath(result.issues.filter((issue) => !dismissed.has(issue.path)))
        : new Map(),
    [dismissed, result],
  );
  const at = (path: string) => (visible.get(path) ?? {}) as { error?: string; warning?: string };

  const syncUrl = (nextAsOf: string, nextType: DecisionType) => {
    const params = new URLSearchParams({
      company: context.companyId,
      asOf: nextAsOf,
      type: nextType,
    });
    window.history.replaceState(null, "", `/decisions?${params.toString()}`);
  };

  const touch = (...paths: string[]) => {
    setDismissed((current) => new Set([...current, ...paths]));
  };

  const update = (change: (form: DecisionForm) => DecisionForm, ...paths: string[]) => {
    setForms((current) => ({
      ...current,
      [type]: change(current[type] ?? defaultDecisionForm(type, asOf)),
    }));
    touch(...paths);
  };

  const changeAsOf = (next: string) => {
    setForms((current) => {
      const moved: Partial<Record<DecisionType, DecisionForm>> = {};
      for (const [key, form] of Object.entries(current) as [DecisionType, DecisionForm][]) {
        moved[key] = moveDefaultDates(form, asOf, next);
      }
      return moved;
    });
    setAsOf(next);
    touch("as_of");
    syncUrl(next, type);
  };

  const changeType = (next: DecisionType) => {
    setType(next);
    syncUrl(asOf, next);
  };

  const reset = () => {
    setForms((current) => ({ ...current, [type]: defaultDecisionForm(type, asOf) }));
    setHorizon(String(CATALOG.horizon_quarters.default));
    setAnnouncement(`${spec.label}: reset to the documented defaults.`);
  };

  const validate = (event: { preventDefault: () => void }) => {
    event.preventDefault();
    setResult(validateScenario(scenario, context));
    setDismissed(new Set());
    setAnnouncement("");
    // Move focus to the result, as for an error summary after submitting a form.
    requestAnimationFrame(() => headingRef.current?.focus());
  };

  const unitSpec = unitSpecFor(spec, decision.magnitude.unit || undefined);
  const magnitudeUnit = unitSpec ? DISPLAY_UNITS[unitSpec.value_unit].symbol : "unit?";
  const blockedReason = !result
    ? "Validate first: Run needs a checked decision."
    : state?.state === "stale_as_of"
      ? "Stale — requires rerun: validate again for the new cutoff."
      : state?.state === "changed"
        ? "Validate again: inputs changed since the last check."
        : result.errors > 0
          ? "Fix the errors first."
          : null;

  const group = spec.share_group;
  const groupKeys = group?.members.map((member) => member.key) ?? [];
  const total = group ? shareTotal(decision.shares, groupKeys) : null;
  const uncertain = spec.parameters.filter((parameter) => parameter.uncertain);

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="flex min-w-0 flex-col gap-10">
        <form
          id={formId}
          noValidate
          onSubmit={validate}
          className="flex flex-col gap-10"
          aria-label="Decision"
        >
          <section aria-labelledby="cutoff-title" className="flex flex-col gap-4">
            <h2 id="cutoff-title" className="font-display text-h3 text-ink">
              Knowledge cutoff and horizon
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <SelectField
                id={fieldId("as_of")}
                label="Known as of"
                hint="Only figures filed by the end of this day are used."
                value={asOf}
                error={at("as_of").error}
                warning={at("as_of").warning}
                onChange={(event) => changeAsOf(event.target.value)}
              >
                {context.cutoffs.map((facts) => (
                  <option key={facts.asOf} value={facts.asOf}>
                    {facts.asOf}
                  </option>
                ))}
              </SelectField>
              <NumberField
                id={fieldId("horizon_quarters")}
                label={CATALOG.horizon_quarters.label}
                hint={`${CATALOG.horizon_quarters.explanation} ${defaultText(CATALOG.horizon_quarters)}`}
                unit="quarters"
                value={horizon}
                valueText={`${horizon} quarters`}
                onChange={(value) => {
                  setHorizon(value);
                  touch("horizon_quarters");
                }}
                slider={sliderFor(CATALOG.horizon_quarters, "quarters")}
                error={at("horizon_quarters").error}
                warning={at("horizon_quarters").warning}
              />
            </div>
          </section>

          <section aria-labelledby="type-title" className="flex flex-col gap-4">
            <h2 id="type-title" className="font-display text-h3 text-ink">
              Decision type
            </h2>
            <DecisionTypePicker value={type} onChange={changeType} />
            <MechanismPanel spec={spec} className="lg:hidden" />
          </section>

          <section aria-labelledby="size-title" className="flex flex-col gap-4">
            <h2 id="size-title" className="font-display text-h3 text-ink">
              Size and timing
            </h2>
            <p className="max-w-prose text-small text-ink-muted">{spec.magnitude.explanation}</p>
            <div className="grid gap-4 sm:grid-cols-2">
              {spec.magnitude.units.length > 1 ? (
                <SelectField
                  id={fieldId("decision.magnitude.unit")}
                  label="Measured against"
                  required
                  value={decision.magnitude.unit}
                  error={at("decision.magnitude.unit").error}
                  hint="Required: the unit changes what the number means."
                  onChange={(event) => {
                    const unit = event.target.value as MagnitudeUnit | "";
                    const next = unitSpecFor(spec, unit || undefined);
                    update(
                      (form) => ({
                        ...form,
                        magnitude: {
                          unit,
                          value:
                            form.magnitude.value.trim() === "" && next
                              ? toInput(next.default_value, next.value_unit)
                              : form.magnitude.value,
                        },
                      }),
                      "decision.magnitude.unit",
                      "decision.magnitude.value",
                    );
                  }}
                >
                  <option value="">Choose a unit</option>
                  {spec.magnitude.units.map((unit) => (
                    <option key={unit.unit} value={unit.unit}>
                      {unit.label}
                    </option>
                  ))}
                </SelectField>
              ) : null}
              <NumberField
                id={fieldId("decision.magnitude.value")}
                label={spec.magnitude.label}
                required
                unit={magnitudeUnit}
                value={decision.magnitude.value}
                valueText={
                  unitSpec
                    ? `${decision.magnitude.value} ${unitSpec.label}`
                    : `${decision.magnitude.value}, unit not chosen`
                }
                hint={unitSpec ? magnitudeHint(unitSpec) : "Choose the unit first."}
                onChange={(value) =>
                  update(
                    (form) => ({ ...form, magnitude: { ...form.magnitude, value } }),
                    "decision.magnitude.value",
                  )
                }
                slider={unitSpec ? sliderFor(unitSpec, unitSpec.value_unit) : undefined}
                error={at("decision.magnitude.value").error}
                warning={at("decision.magnitude.value").warning}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {(["announcement_date", "effective_date"] as const).map((key) => (
                <TextField
                  key={key}
                  id={fieldId(`decision.timing.${key}`)}
                  type="date"
                  label={key === "announcement_date" ? "Announced on" : "Takes effect on"}
                  hint={
                    key === "announcement_date"
                      ? "On or after the cutoff."
                      : "On or after the announcement."
                  }
                  value={decision.timing[key]}
                  error={at(`decision.timing.${key}`).error}
                  onChange={(event) =>
                    update(
                      (form) => ({
                        ...form,
                        timing: { ...form.timing, [key]: event.target.value },
                      }),
                      `decision.timing.${key}`,
                    )
                  }
                />
              ))}
              {[spec.lag_quarters, spec.ramp_quarters].map((timing) => {
                const key = timing.key as "lag_quarters" | "ramp_quarters";
                const path = `decision.timing.${key}`;
                return (
                  <NumberField
                    key={key}
                    id={fieldId(path)}
                    label={timing.label}
                    hint={timing.explanation}
                    unit="quarters"
                    value={decision.timing[key]}
                    valueText={`${decision.timing[key]} quarters`}
                    onChange={(value) =>
                      update(
                        (form) => ({ ...form, timing: { ...form.timing, [key]: value } }),
                        path,
                      )
                    }
                    slider={sliderFor(timing, "quarters")}
                    error={at(path).error}
                    warning={at(path).warning}
                  />
                );
              })}
            </div>
          </section>

          <section aria-labelledby="assumptions-title" className="flex flex-col gap-6">
            <h2 id="assumptions-title" className="font-display text-h3 text-ink">
              Assumptions
            </h2>
            {spec.parameters.map((parameter) => {
              const path = `decision.${parameter.key}`;
              const unit = DISPLAY_UNITS[parameter.unit];
              const hint = `${parameter.explanation} ${defaultText(parameter)}`;
              if (parameter.uncertain) {
                const field = decision.distributions[parameter.key];
                if (!field) return null;
                return (
                  <DistributionInput
                    key={parameter.key}
                    id={fieldId(path)}
                    label={parameter.label}
                    hint={hint}
                    unit={unit.symbol}
                    field={field}
                    onChange={(next: DistributionField) =>
                      update(
                        (form) => ({
                          ...form,
                          distributions: { ...form.distributions, [parameter.key]: next },
                        }),
                        path,
                        `${path}.value`,
                        `${path}.low`,
                        `${path}.mode`,
                        `${path}.high`,
                      )
                    }
                    error={at(path).error}
                    warning={at(path).warning}
                    pointErrors={{
                      ...(at(`${path}.value`).error ? { value: at(`${path}.value`).error } : {}),
                      ...(at(`${path}.low`).error ? { low: at(`${path}.low`).error } : {}),
                      ...(at(`${path}.mode`).error ? { mode: at(`${path}.mode`).error } : {}),
                      ...(at(`${path}.high`).error ? { high: at(`${path}.high`).error } : {}),
                    }}
                  />
                );
              }
              const value = decision.scalars[parameter.key] ?? "";
              return (
                <NumberField
                  key={parameter.key}
                  id={fieldId(path)}
                  label={parameter.label}
                  hint={hint}
                  unit={unit.symbol}
                  value={value}
                  valueText={`${value} ${unit.name}`}
                  onChange={(next) =>
                    update(
                      (form) => ({ ...form, scalars: { ...form.scalars, [parameter.key]: next } }),
                      path,
                    )
                  }
                  slider={sliderFor(parameter, parameter.unit)}
                  error={at(path).error}
                  warning={at(path).warning}
                />
              );
            })}
          </section>

          {group ? (
            <section aria-labelledby="shares-title" className="flex flex-col gap-4">
              <h2 id="shares-title" className="font-display text-h3 text-ink">
                {group.label}
              </h2>
              <SharesInput
                id={fieldId(`decision.${group.key}`)}
                label={`${group.label} shares`}
                explanation={group.explanation}
                members={group.members}
                values={decision.shares}
                onChange={(key, value) =>
                  update(
                    (form) => ({ ...form, shares: { ...form.shares, [key]: value } }),
                    `decision.${group.key}`,
                    `decision.${group.key}.${key}`,
                    "decision.new_debt_interest_rate",
                  )
                }
                total={total === null ? null : `${total}%`}
                complete={total === "100"}
                error={at(`decision.${group.key}`).error}
                warning={at(`decision.${group.key}`).warning}
                memberErrors={Object.fromEntries(
                  groupKeys.map((key) => [key, at(`decision.${group.key}.${key}`).error]),
                )}
              />
            </section>
          ) : null}

          <section aria-labelledby="sensitivity-title" className="flex flex-col gap-4">
            <h2 id="sensitivity-title" className="font-display text-h3 text-ink">
              Sensitivity
            </h2>
            <fieldset
              id={fieldId("sensitivity.parameters")}
              className="flex flex-col gap-3"
              aria-describedby="sensitivity-hint"
            >
              <legend className="text-small font-medium text-ink">Vary one at a time</legend>
              <p id="sensitivity-hint" className="-mt-1 text-small text-ink-muted">
                A run varies each chosen range across its values while the others stay at their
                central value. Up to {CATALOG.sensitivity_max_parameters} parameters; a fixed value
                has no range to vary.
              </p>
              {uncertain.map((parameter) => {
                const checked = decision.sensitivity.parameters.includes(parameter.key);
                const fixed = decision.distributions[parameter.key]?.shape === "fixed";
                return (
                  <CheckboxField
                    key={parameter.key}
                    id={`sensitivity-${parameter.key}`}
                    label={parameter.label}
                    checked={checked}
                    {...(fixed ? { hint: "Fixed value: give it a range to vary it." } : {})}
                    onChange={(event) =>
                      update(
                        (form) => ({
                          ...form,
                          sensitivity: {
                            ...form.sensitivity,
                            parameters: event.target.checked
                              ? [...form.sensitivity.parameters, parameter.key]
                              : form.sensitivity.parameters.filter((key) => key !== parameter.key),
                          },
                        }),
                        "sensitivity.parameters",
                      )
                    }
                  />
                );
              })}
              {at("sensitivity.parameters").error ? (
                <p className="text-small text-negative">{at("sensitivity.parameters").error}</p>
              ) : null}
            </fieldset>
            <div className="max-w-xs">
              <SelectField
                id={fieldId("sensitivity.points")}
                label="Points per parameter"
                value={decision.sensitivity.points}
                onChange={(event) =>
                  update(
                    (form) => ({
                      ...form,
                      sensitivity: { ...form.sensitivity, points: event.target.value },
                    }),
                    "sensitivity.points",
                  )
                }
              >
                {CATALOG.sensitivity_points.map((points) => (
                  <option key={points} value={String(points)}>
                    {points}
                  </option>
                ))}
              </SelectField>
            </div>
          </section>
        </form>

        {/*
          The actions sit after the form: the Run and Save dialogs hold their own forms, and a
          form inside a form is invalid HTML (the browser drops the inner one). Validate stays
          the form's submit button through the form attribute.
        */}
        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-6">
          <Button
            type="submit"
            form={formId}
            variant={blockedReason === null ? "secondary" : "primary"}
          >
            Validate
          </Button>
          <Button type="button" variant="secondary" onClick={reset}>
            <RotateCcw aria-hidden="true" />
            Reset to defaults
          </Button>
          <RunDialog
            draft={state?.state === "fresh" ? (result?.draft ?? null) : null}
            blockedReason={blockedReason}
          />
          <SaveToNotebook
            draft={state?.state === "fresh" ? (result?.draft ?? null) : null}
            blockedReason={blockedReason}
            defaultName={`${context.name}: ${spec.label} at ${asOf}`.slice(0, 120)}
            target={saved}
            onSaved={setSaved}
          />
          <p role="status" className="basis-full text-small text-ink-muted empty:hidden">
            {announcement}
          </p>
        </div>

        <ValidationPanel result={result} freshness={state} headingRef={headingRef} />
      </div>

      <aside className="hidden lg:block">
        <div className="sticky top-24">
          <MechanismPanel spec={spec} />
        </div>
      </aside>
    </div>
  );
}
