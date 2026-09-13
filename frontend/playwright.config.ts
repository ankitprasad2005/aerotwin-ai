import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  // fullyParallel only serializes tests within a single file; these specs hit a
  // real, unseeded, shared backend/Postgres/WebSocket with no mocking, so cross-file
  // parallelism (Playwright's default, CPU-core-based worker count) risks two specs'
  // real orchestration runs interleaving. Force one worker for genuine serialization.
  workers: 1,
  retries: 0,
  timeout: 30000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
