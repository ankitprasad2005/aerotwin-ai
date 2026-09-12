import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary"],
      include: ["src/**/*.{ts,tsx}"],
      // src/types/** is type-only (interfaces/type aliases erase at compile time,
      // so v8 can never report real coverage for it — same reasoning as *.d.ts).
      exclude: ["src/main.tsx", "src/test/**", "src/**/*.d.ts", "src/types/**"],
      thresholds: { lines: 95, statements: 95, functions: 90, branches: 85 },
    },
  },
});
