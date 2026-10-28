import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface ColorToken {
  name: string;
  hex: string;
}

/** Parses the colour tokens out of tokens.css, so the CSS file stays the single source. */
export function parseColorTokens(css: string): ColorToken[] {
  const tokens: ColorToken[] = [];
  for (const match of css.matchAll(/--color-([a-z-]+):\s*(#[0-9a-f]{6})\s*;/gi)) {
    const [, name, hex] = match;
    if (name && hex) tokens.push({ name, hex: hex.toLowerCase() });
  }
  return tokens;
}

/** Reads tokens.css at build time (server only). `cwd` is the app root when Next.js or vitest run. */
export function readColorTokens(appRoot: string = process.cwd()): ColorToken[] {
  const css = readFileSync(join(appRoot, "src", "tokens", "tokens.css"), "utf8");
  return parseColorTokens(css);
}

export function tokenHex(tokens: ColorToken[], name: string): string {
  const token = tokens.find((candidate) => candidate.name === name);
  if (!token) throw new Error(`Unknown colour token "${name}"`);
  return token.hex;
}

/** Foreground / background pairs the interface actually uses. */
export const TEXT_PAIRS: ReadonlyArray<readonly [foreground: string, background: string]> = [
  ["ink", "canvas"],
  ["ink", "surface"],
  ["ink", "inset"],
  ["ink-muted", "canvas"],
  ["ink-muted", "surface"],
  ["ink-muted", "inset"],
  ["mint", "canvas"],
  ["mint", "surface"],
  ["blue", "canvas"],
  ["blue", "surface"],
  ["violet", "canvas"],
  ["violet", "surface"],
  ["observed", "surface"],
  ["warning", "surface"],
  ["warning", "inset"],
  ["negative", "surface"],
  ["negative", "inset"],
  ["canvas", "mint"],
  ["canvas", "mint-strong"],
];

export const NON_TEXT_PAIRS: ReadonlyArray<readonly [foreground: string, background: string]> = [
  ["line-strong", "canvas"],
  ["line-strong", "surface"],
  ["line-strong", "inset"],
  ["mint", "canvas"],
  ["mint", "surface"],
  ["mint", "inset"],
  // Chart lines are graphical objects: 3:1 against the chart surface (WCAG 1.4.11).
  ["observed", "surface"],
  ["series-baseline", "surface"],
  ["series-alt-a", "surface"],
  ["series-alt-b", "surface"],
];
