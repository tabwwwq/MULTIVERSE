/*
 * Numbers on result screens. A value is rounded to what its interval allows (PRD
 * FP-02): with a p10-p90 width of USD 840m, "USD 1.7bn" is honest and "USD 1,672.3m"
 * is false precision. Formatting is display only; exports keep the exact strings.
 */

export type ValueUnit = "usd" | "fraction";

const MINUS = "−";

function sign(value: number, signed: boolean): string {
  if (value < 0) return MINUS;
  return signed && value > 0 ? "+" : "";
}

/** Decimals that keep one significant digit of the interval width, and no more. */
function decimalsFor(step: number | undefined, scale: number, max = 2): number {
  if (step === undefined || step <= 0) return 1;
  const inUnit = step / scale;
  return Math.max(0, Math.min(max, -Math.floor(Math.log10(inUnit))));
}

export interface FormatOptions {
  signed?: boolean;
  /** p90 - p10, in the same unit as the value: limits the shown precision. */
  width?: number;
}

export function formatValue(value: number, unit: ValueUnit, options: FormatOptions = {}): string {
  const { signed = false, width } = options;
  const size = Math.abs(value);
  const step = width;
  if (unit === "fraction") {
    const decimals = decimalsFor(step, 0.01, 1);
    return `${sign(value, signed)}${(size * 100).toFixed(decimals)}%`;
  }
  const billions = size >= 1e9;
  const scale = billions ? 1e9 : 1e6;
  const decimals = width === undefined ? 1 : decimalsFor(step, scale);
  const text = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(size / scale);
  return `${sign(value, signed)}USD ${text}${billions ? "bn" : "m"}`;
}

/** Short axis label: "1.5bn", "800m", "+10%". */
export function formatTick(value: number, unit: ValueUnit, signed: boolean): string {
  if (unit === "fraction")
    return `${sign(value, signed)}${Math.round(Math.abs(value) * 1000) / 10}%`;
  const size = Math.abs(value);
  if (size === 0) return "0";
  const text =
    size >= 1e9
      ? `${Number((size / 1e9).toFixed(2))}bn`
      : `${Number((size / 1e6).toFixed(size >= 1e8 ? 0 : 1))}m`;
  return `${sign(value, signed)}${text}`;
}

/** "USD 1.7bn (p10 USD 1.3bn to p90 USD 2.1bn)" with precision limited by the interval. */
export function formatQuantiles(
  point: { p10: number; p50: number; p90: number },
  unit: ValueUnit,
  signed = false,
): { median: string; range: string } {
  const width = point.p90 - point.p10;
  const options = width > 0 ? { signed, width } : { signed };
  return {
    median: formatValue(point.p50, unit, options),
    range: `${formatValue(point.p10, unit, options)} to ${formatValue(point.p90, unit, options)}`,
  };
}
