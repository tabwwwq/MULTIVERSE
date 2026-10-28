import type { Scale } from "@/companies/params";

/*
 * Display formatting only. Amounts arrive as exact decimal strings; converting to a
 * number here is fine for showing millions or billions, never for calculations.
 */

const FORMATTERS: Record<Scale, Intl.NumberFormat> = {
  m: new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }),
  bn: new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
};

const DIVISORS: Record<Scale, number> = { m: 1e6, bn: 1e9 };

export function formatAmount(value: string, scale: Scale): string {
  const formatted = FORMATTERS[scale].format(Number(value) / DIVISORS[scale]);
  // Use a true minus sign so negative figures align and read clearly.
  return formatted.replace(/^-/, "−");
}

export function unitLabel(currency: string, scale: Scale): string {
  return `${currency} ${scale}`;
}
