// ESLint flat config for all TypeScript and JavaScript in the repository (ADR-0009).
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig(
  {
    ignores: [
      "**/node_modules/**",
      "**/generated/**",
      "**/dist/**",
      "**/.next/**",
      ".venv/**",
      "var/**",
    ],
  },
  js.configs.recommended,
  tseslint.configs.strict,
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
    files: ["packages/contracts/ts/src/index.ts"],
    rules: { "no-restricted-imports": "off" },
  },
);
