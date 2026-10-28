import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    // Playwright specs in e2e/ run with `npm run test:e2e`, not with vitest.
    include: ["test/**/*.test.ts"],
    environment: "node",
  },
});
