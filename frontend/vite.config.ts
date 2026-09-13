import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // e2e/**/*.spec.ts are Playwright specs (real browser, real docker-compose
    // stack) — they import `test`/`expect` from @playwright/test, not Vitest's
    // globals, so Vitest's default glob would otherwise try and fail to collect
    // them as unit tests. Spread the built-in defaults rather than replace them,
    // so dist/**, node_modules/**, etc. stay excluded too.
    exclude: [...configDefaults.exclude, "e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary"],
      include: ["src/**/*.{ts,tsx}"],
      // src/types/** is type-only (interfaces/type aliases erase at compile time,
      // so v8 can never report real coverage for it — same reasoning as *.d.ts).
      exclude: ["src/main.tsx", "src/test/**", "src/**/*.d.ts", "src/types/**"],
      thresholds: { lines: 95, statements: 95, functions: 95, branches: 95 },
    },
  },
});
