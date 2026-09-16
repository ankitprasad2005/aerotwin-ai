import { expect, test } from "@playwright/test";

test("starting a run updates the graph and activity feed live", async ({ page }) => {
  await page.goto("/orchestration");

  await page.getByPlaceholder(/Improve airline profitability/).fill("Improve airline profitability");
  await page.getByRole("button", { name: /RUN ORCHESTRATION/ }).click();

  // POST /api/runs blocks until the full pipeline completes, including two
  // sequential real LLM calls (NETWORK_AGENT then FLEET_AGENT) — this wait is
  // where essentially all of that latency lands, so it gets a much wider budget
  // than the rest of the test.
  const executionGraph = page.getByTestId("execution-graph");
  await expect(executionGraph).toBeVisible({ timeout: 60000 });
  // Scoped to the graph itself: an unscoped page-wide match also hits the run
  // picker's <option> text (which also carries the run's status in parentheses)
  // — that option is a real match but hidden while the <select> is collapsed.
  await expect(executionGraph.getByText(/COMPLETED|FAILED/).first()).toBeVisible({ timeout: 15000 });

  // The run's combined output on the page itself: each agent's recommendation plus the decision
  // reconciled from them (the slide-overs show the same data, but one node at a time).
  const runOutput = page.getByTestId("run-output");
  await expect(runOutput).toBeVisible({ timeout: 15000 });
  await expect(runOutput.getByTestId("agent-output")).toHaveCount(2);
  await expect(runOutput).toContainText("NETWORK AGENT");
  await expect(runOutput).toContainText("FLEET AGENT");
  await expect(page.getByTestId("final-decision-output")).toContainText("frequency");

  // Client-side navigation (not page.goto), deliberately: a full page load tears
  // down the WebSocket connection and the in-memory live event-stream store, which
  // has no REST backfill by design — going through the Sidebar link instead
  // preserves the SPA session so the just-completed run's events are still there.
  await page.getByRole("link", { name: "DASHBOARD" }).click();
  // "ORCHESTRATOR" is the source label for every orchestration.* event from any
  // run (formatEvent.ts doesn't render per-run detail outside debug mode), so this
  // check would be satisfied by a concurrently in-flight run's own events if one
  // existed — safe only because playwright.config.ts forces workers: 1, guaranteeing
  // this is the only run in flight in the whole E2E suite.
  await expect(page.getByTestId("activity-feed")).toContainText("ORCHESTRATOR", { timeout: 15000 });
});
