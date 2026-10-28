import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { NON_TEXT_PAIRS, TEXT_PAIRS, readColorTokens, tokenHex } from "@/tokens/color-tokens";
import { MIN_NON_TEXT_CONTRAST, MIN_TEXT_CONTRAST, contrastRatio } from "@/tokens/contrast";

const APP_ROOT = fileURLToPath(new URL("..", import.meta.url));
const tokens = readColorTokens(APP_ROOT);

describe("contrast helper", () => {
  it("matches the WCAG reference values", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
    expect(contrastRatio("#ffffff", "#ffffff")).toBe(1);
  });

  it("rejects colours that are not #rrggbb", () => {
    expect(() => contrastRatio("mint", "#ffffff")).toThrow();
  });
});

describe("design tokens", () => {
  it("are read from tokens.css", () => {
    const names = tokens.map((token) => token.name);
    expect(names).toEqual(
      expect.arrayContaining(["canvas", "surface", "inset", "ink", "ink-muted", "mint"]),
    );
  });

  it("use the exact palette of docs/10_DESIGN_SYSTEM.md", () => {
    const brief: Record<string, string> = {
      canvas: "#07101b",
      surface: "#0d1928",
      inset: "#102536",
      line: "#254255",
      mint: "#5deec9",
      blue: "#6389ef",
      violet: "#ad8cff",
      ink: "#eef6f7",
      "ink-muted": "#91aaba",
      warning: "#ffc673",
      negative: "#ff8496",
    };
    for (const [name, hex] of Object.entries(brief)) expect(tokenHex(tokens, name)).toBe(hex);
  });

  it.each(TEXT_PAIRS)("text %s on %s meets 4.5:1", (foreground, background) => {
    const value = contrastRatio(tokenHex(tokens, foreground), tokenHex(tokens, background));
    expect(value).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST);
  });

  it.each(NON_TEXT_PAIRS)("boundary %s on %s meets 3:1", (foreground, background) => {
    const value = contrastRatio(tokenHex(tokens, foreground), tokenHex(tokens, background));
    expect(value).toBeGreaterThanOrEqual(MIN_NON_TEXT_CONTRAST);
  });

  it("keeps the decorative line token out of control boundaries", () => {
    // #254255 is only 1.8:1 on canvas, which is why line-strong exists.
    expect(contrastRatio(tokenHex(tokens, "line"), tokenHex(tokens, "canvas"))).toBeLessThan(
      MIN_NON_TEXT_CONTRAST,
    );
  });
});
