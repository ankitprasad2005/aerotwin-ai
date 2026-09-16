import { expect, test } from "@playwright/test";

test("starting a run updates the graph and activity feed live", async ({ page }) => {
  // Two full pipelines (the run plus a follow-up prompt), each two real LLM calls.
  test.setTimeout(240000);
  await page.goto("/orchestration");

  await page.getByPlaceholder(/Improve airline profitability/).fill("Improve airline profitability");
  await page.getByRole("button", { name: /RUN ORCHESTRATION/ }).click();

  // POST /api/runs blocks until the full pipeline completes, including two sequential real LLM
  // calls (NETWORK_AGENT then FLEET_AGENT) — this wait is where essentially all of that latency
  // lands, so it gets a much wider budget than the rest of the test. The finished run opens on its
  // OUTPUT tab: each agent's recommendation plus the decision reconciled from them.
  const runOutput = page.getByTestId("run-output");
  await expect(runOutput).toBeVisible({ timeout: 60000 });
  await expect(runOutput.getByTestId("agent-output")).toHaveCount(2);
  await expect(runOutput).toContainText("NETWORK AGENT");
  await expect(runOutput).toContainText("FLEET AGENT");
  await expect(page.getByTestId("final-decision-output")).toContainText("frequency");

  // Execution graph and knowledge graph are tabs of the selected run.
  await page.getByRole("tab", { name: "EXECUTION GRAPH" }).click();
  const executionGraph = page.getByTestId("execution-graph");
  await expect(executionGraph).toBeVisible({ timeout: 15000 });
  await expect(executionGraph.getByText(/COMPLETED|FAILED/).first()).toBeVisible({ timeout: 15000 });

  await page.getByRole("tab", { name: "KNOWLEDGE GRAPH" }).click();
  const knowledgeGraph = page.getByTestId("knowledge-graph");
  await expect(knowledgeGraph).toBeVisible({ timeout: 15000 });
  // What the agents knew: a twin entity they read, and the decision their work produced.
  await expect(knowledgeGraph.getByText("NETWORK AGENT")).toBeVisible();
  await expect(knowledgeGraph.getByText("ROUTE").first()).toBeVisible();

  // A follow-up prompt runs the agents again inside the same run, adding an iteration.
  await page.getByRole("tab", { name: "PROMPT" }).click();
  await page.getByLabel("Follow-up prompt").fill("Now protect load factor on the thin routes");
  await page.getByRole("button", { name: /ADD PROMPT/ }).click();
  await page.getByRole("tab", { name: "OUTPUT" }).click();
  await expect(page.getByTestId("run-iteration")).toHaveCount(2, { timeout: 90000 });

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
