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
  // Global per-test wall-clock ceiling — this caps the ENTIRE test regardless of any
  // individual expect(...).toBeVisible({ timeout: N }) override, so it must be wide
  // enough to cover orchestration-run.spec.ts's real, synchronous, two-sequential-
  // real-LLM-call pipeline (its own 60s assertion timeout would otherwise be
  // silently truncated by this smaller global ceiling) plus the rest of that test.
  timeout: 90000,
  use: {
    // Matches docker-compose.yml's frontend host-published port.
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3005",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
