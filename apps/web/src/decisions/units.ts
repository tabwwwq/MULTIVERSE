import type { ValueUnit } from "@multiverse/contracts";
import { type DecimalInput, shift, toDecimalString, toNumber } from "@/lib/decimal";

/*
 * How contract values are shown and typed. Contracts store fractions (0.4) and whole
 * dollars; people type percent (40) and millions of dollars (400). Conversion is an
 * exact power-of-ten shift, never a floating-point multiplication.
 */

export interface DisplayUnit {
  /** Shown next to the input, e.g. "%" or "USD m". */
  symbol: string;
  /** Spoken and written in full, e.g. "percent". */
  name: string;
  /** Contract value = typed value × 10^exponent. */
  exponent: number;
}

export const DISPLAY_UNITS: Record<ValueUnit, DisplayUnit> = {
  fraction: { symbol: "%", name: "percent", exponent: -2 },
  percentage_points: { symbol: "p.p.", name: "percentage points", exponent: 0 },
  usd: { symbol: "USD m", name: "million US dollars", exponent: 6 },
  quarters: { symbol: "quarters", name: "quarters", exponent: 0 },
  years: { symbol: "years", name: "years", exponent: 0 },
  months_of_salary: { symbol: "months", name: "months of salary", exponent: 0 },
};

/** Contract value to the number a person types, e.g. "0.4" (fraction) to "40". */
export function toInput(value: DecimalInput, unit: ValueUnit): string {
  return toDecimalString(shift(value, -DISPLAY_UNITS[unit].exponent));
}

/** Typed number back to the contract value, e.g. "40" (percent) to "0.4". */
export function fromInput(value: string, unit: ValueUnit): string {
  return toDecimalString(shift(value, DISPLAY_UNITS[unit].exponent));
}

const plain = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const oneDecimal = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function signOf(value: number, signed: boolean): string {
  if (value < 0) return "−";
  return signed && value > 0 ? "+" : "";
}

/** Dollars as "USD 412.5m" or "USD 1.2bn"; uses a true minus sign. */
export function formatUsd(value: DecimalInput, signed = false): string {
  const amount = toNumber(value);
  const size = Math.abs(amount);
  const sign = signOf(amount, signed);
  if (size >= 1e9) return `${sign}USD ${oneDecimal.format(size / 1e9)}bn`;
  return `${sign}USD ${oneDecimal.format(size / 1e6)}m`;
}

/** A contract value with its unit, for hints, messages and summaries. */
export function formatValue(value: DecimalInput, unit: ValueUnit, signed = false): string {
  if (unit === "usd") return formatUsd(value, signed);
  const shown = toNumber(shift(value, -DISPLAY_UNITS[unit].exponent));
  const text = `${signOf(shown, signed)}${plain.format(Math.abs(shown))}`;
  switch (unit) {
    case "fraction":
      return `${text}%`;
    case "percentage_points":
      return `${text} p.p.`;
    default:
      return `${text} ${DISPLAY_UNITS[unit].symbol}`;
  }
}
