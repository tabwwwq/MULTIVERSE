/*
 * Exact decimal arithmetic on BigInt for contract values (ADR-0008: money and shares are
 * decimal strings). JavaScript numbers are only used to *display* a result, never to
 * compare or add values: 0.1 + 0.2 + 0.7 must be exactly 1 when financing shares are
 * checked (PRD FR-DE-04).
 */

const DECIMAL = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/;

export interface Dec {
  /** value = coef / 10^scale */
  coef: bigint;
  scale: number;
}

export type DecimalInput = string | Dec;

/** The contract format: no exponent, no leading zeros, no plus sign. */
export function isDecimal(value: string): boolean {
  return DECIMAL.test(value);
}

export function dec(value: DecimalInput): Dec {
  if (typeof value !== "string") return value;
  if (!isDecimal(value)) throw new Error(`Not a decimal string: ${value}`);
  const [whole = "0", fraction = ""] = value.split(".");
  return { coef: BigInt(whole + fraction), scale: fraction.length };
}

function rescale(value: Dec, scale: number): bigint {
  return value.coef * 10n ** BigInt(scale - value.scale);
}

function align(a: Dec, b: Dec): [bigint, bigint, number] {
  const scale = Math.max(a.scale, b.scale);
  return [rescale(a, scale), rescale(b, scale), scale];
}

export function compare(a: DecimalInput, b: DecimalInput): -1 | 0 | 1 {
  const [x, y] = align(dec(a), dec(b));
  return x < y ? -1 : x > y ? 1 : 0;
}

export function isZero(value: DecimalInput): boolean {
  return dec(value).coef === 0n;
}

export function add(a: DecimalInput, b: DecimalInput): Dec {
  const [x, y, scale] = align(dec(a), dec(b));
  return { coef: x + y, scale };
}

export function sub(a: DecimalInput, b: DecimalInput): Dec {
  const [x, y, scale] = align(dec(a), dec(b));
  return { coef: x - y, scale };
}

export function mul(a: DecimalInput, b: DecimalInput): Dec {
  const x = dec(a);
  const y = dec(b);
  return { coef: x.coef * y.coef, scale: x.scale + y.scale };
}

export function abs(value: DecimalInput): Dec {
  const x = dec(value);
  return { coef: x.coef < 0n ? -x.coef : x.coef, scale: x.scale };
}

/** Multiply by 10^exponent exactly, e.g. a fraction to percent with exponent 2. */
export function shift(value: DecimalInput, exponent: number): Dec {
  const x = dec(value);
  if (exponent >= 0) return { coef: x.coef * 10n ** BigInt(exponent), scale: x.scale };
  return { coef: x.coef, scale: x.scale - exponent };
}

/** a / b rounded half away from zero to `scale` decimals. */
export function div(a: DecimalInput, b: DecimalInput, scale = 0): Dec {
  const x = dec(a);
  const y = dec(b);
  if (y.coef === 0n) throw new Error("Division by zero");
  // a / b = (x.coef / 10^xs) / (y.coef / 10^ys); scale the numerator to keep `scale` digits.
  const numerator = x.coef * 10n ** BigInt(scale + y.scale + 1);
  const denominator = y.coef * 10n ** BigInt(x.scale);
  const tenfold = numerator / denominator;
  const rounded = (tenfold + (tenfold < 0n ? -5n : 5n)) / 10n;
  return { coef: rounded, scale };
}

/** Canonical decimal string: trailing zeros dropped, "-0" becomes "0". */
export function toDecimalString(value: DecimalInput): string {
  let { coef, scale } = dec(value);
  while (scale > 0 && coef % 10n === 0n) {
    coef /= 10n;
    scale -= 1;
  }
  if (scale < 0) {
    coef *= 10n ** BigInt(-scale);
    scale = 0;
  }
  const negative = coef < 0n;
  const digits = (negative ? -coef : coef).toString().padStart(scale + 1, "0");
  const whole = digits.slice(0, digits.length - scale);
  const fraction = digits.slice(digits.length - scale);
  const text = fraction ? `${whole}.${fraction}` : whole;
  return negative ? `-${text}` : text;
}

/** For display only. */
export function toNumber(value: DecimalInput): number {
  return Number(toDecimalString(value));
}

/**
 * Read what a person typed: surrounding spaces, a leading "+", a typographic minus and
 * a trailing decimal point are accepted. Thousands separators and exponents are not:
 * "1,5" could mean 1.5 or 15, so it is rejected rather than guessed.
 */
export function parseUserDecimal(input: string): string | null {
  let text = input.trim().replace(/^−/, "-");
  if (text.startsWith("+")) text = text.slice(1);
  if (text.endsWith(".")) text = text.slice(0, -1);
  if (text.startsWith(".")) text = `0${text}`;
  if (text.startsWith("-.")) text = `-0${text.slice(1)}`;
  if (!/^-?[0-9]+(\.[0-9]+)?$/.test(text)) return null;
  const negative = text.startsWith("-");
  const unsigned = (negative ? text.slice(1) : text).replace(/^0+(?=[0-9])/, "");
  return toDecimalString(negative ? `-${unsigned}` : unsigned);
}
