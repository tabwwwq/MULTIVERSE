import { ChevronDown, CircleAlert, TriangleAlert } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

/*
 * Form controls follow the forms guidance: visible labels above the control,
 * hints and errors linked with aria-describedby, errors shown with an icon and
 * text (never colour alone), 16px text and 48px targets, native elements only.
 */

export const CONTROL =
  "min-h-12 w-full rounded-control border border-line-strong bg-inset px-3 text-body text-ink " +
  "placeholder:text-ink-muted disabled:cursor-not-allowed disabled:border-line disabled:text-ink-muted " +
  "aria-invalid:border-negative user-invalid:border-negative";

interface FieldShellProps {
  id: string;
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  /** A non-blocking note, e.g. "outside the planning range". */
  warning?: string | undefined;
  required?: boolean | undefined;
  children: ReactNode;
}

export function describedBy(
  id: string,
  hint?: string,
  error?: string,
  warning?: string,
): string | undefined {
  const ids = [
    hint ? `${id}-hint` : null,
    error ? `${id}-error` : null,
    warning ? `${id}-warning` : null,
  ].filter(Boolean);
  return ids.length > 0 ? ids.join(" ") : undefined;
}

/** Field message with an icon and text, never colour alone. */
export function FieldMessage({
  id,
  tone,
  children,
}: {
  id: string;
  tone: "error" | "warning";
  children: ReactNode;
}) {
  const Icon = tone === "error" ? CircleAlert : TriangleAlert;
  return (
    <p
      id={id}
      className={`flex items-start gap-1.5 text-small ${tone === "error" ? "text-negative" : "text-warning"}`}
    >
      <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

export function FieldShell({
  id,
  label,
  hint,
  error,
  warning,
  required,
  children,
}: FieldShellProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-small font-medium text-ink">
        {label}
        {required ? <span className="font-normal text-ink-muted"> (required)</span> : null}
      </label>
      {children}
      {hint ? (
        <p id={`${id}-hint`} className="text-small text-ink-muted">
          {hint}
        </p>
      ) : null}
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
    </div>
  );
}

type InputProps = Omit<ComponentProps<"input">, "id"> & {
  id: string;
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  warning?: string | undefined;
  /** Unit shown after the value, e.g. "USD m" or "%". */
  unit?: string;
};

export function TextField({
  id,
  label,
  hint,
  error,
  warning,
  unit,
  required,
  className,
  ...props
}: InputProps) {
  return (
    <FieldShell
      id={id}
      label={label}
      hint={hint}
      error={error}
      warning={warning}
      required={required}
    >
      <div className="flex items-stretch">
        <input
          id={id}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, hint, error, warning)}
          className={cn(CONTROL, unit && "rounded-r-none", className)}
          {...props}
        />
        {unit ? (
          <span
            className="flex items-center rounded-r-control border border-l-0 border-line-strong bg-surface px-3 text-small text-ink-muted"
            aria-hidden="true"
          >
            {unit}
          </span>
        ) : null}
      </div>
    </FieldShell>
  );
}

type SelectProps = Omit<ComponentProps<"select">, "id"> & {
  id: string;
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  warning?: string | undefined;
};

export function SelectField({
  id,
  label,
  hint,
  error,
  warning,
  required,
  className,
  children,
  ...props
}: SelectProps) {
  return (
    <FieldShell
      id={id}
      label={label}
      hint={hint}
      error={error}
      warning={warning}
      required={required}
    >
      <div className="relative">
        <select
          id={id}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, hint, error, warning)}
          className={cn(CONTROL, "appearance-none pr-10", className)}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-muted"
        />
      </div>
    </FieldShell>
  );
}

type CheckboxProps = Omit<ComponentProps<"input">, "id" | "type"> & {
  id: string;
  label: string;
  hint?: string;
};

export function CheckboxField({ id, label, hint, className, ...props }: CheckboxProps) {
  return (
    <div className="flex items-start gap-3">
      <input
        id={id}
        type="checkbox"
        aria-describedby={hint ? `${id}-hint` : undefined}
        className={cn("mt-1 size-5 shrink-0 accent-mint disabled:cursor-not-allowed", className)}
        {...props}
      />
      <div className="flex flex-col gap-0.5">
        <label htmlFor={id} className="text-body text-ink">
          {label}
        </label>
        {hint ? (
          <p id={`${id}-hint`} className="text-small text-ink-muted">
            {hint}
          </p>
        ) : null}
      </div>
    </div>
  );
}
