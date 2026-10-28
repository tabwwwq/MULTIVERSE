// ESLint flat config for all TypeScript and JavaScript in the repository (ADR-0009).
import js from "@eslint/js";
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

const WEB_FILES = ["apps/web/**/*.{js,jsx,mjs,ts,tsx}"];

// Next.js rules (React, hooks, accessibility, Core Web Vitals) apply to the web app only.
const nextForWeb = nextCoreWebVitals
  .filter((config) => !(Object.keys(config).length === 1 && config.ignores))
  .map((config) => ({
    ...config,
    files: WEB_FILES,
    settings: { ...config.settings, next: { rootDir: "apps/web/" } },
  }));

export default defineConfig(
  {
    ignores: [
      "**/node_modules/**",
      "**/generated/**",
      "**/dist/**",
      "**/.next/**",
      "**/next-env.d.ts",
      "**/test-results/**",
      "**/playwright-report/**",
      ".venv/**",
      "var/**",
    ],
  },
  js.configs.recommended,
  tseslint.configs.strict,
  ...nextForWeb,
  {
    files: ["**/*.mjs"],
    languageOptions: { globals: { console: "readonly", process: "readonly" } },
  },
  {
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["**/packages/**", "**/services/**", "**/apps/**", "**/pipelines/**"],
              message:
                "Import another module by its package name (e.g. @multiverse/contracts), not by a relative path (ADR-0009).",
            },
            {
              group: ["@multiverse/*/src/**", "@multiverse/*/scripts/**"],
              message: "Import a package only through its public entry point (ADR-0009).",
            },
            {
              group: ["**/generated/**"],
              message:
                "Generated files are internal; import from the package entry point (ADR-0009).",
            },
          ],
        },
      ],
    },
  },
  {
    // The entry point is the one place allowed to re-export generated files.
    files: ["packages/contracts/ts/src/index.ts", "packages/contracts/ts/src/demo.ts"],
    rules: { "no-restricted-imports": "off" },
  },
);
