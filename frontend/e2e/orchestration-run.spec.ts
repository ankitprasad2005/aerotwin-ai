import { expect, test } from "@playwright/test";

test("starting a run updates the graph and activity feed live", async ({ page }) => {
  await page.goto("/orchestration");

  await page.getByPlaceholder(/Improve airline profitability/).fill("Improve airline profitability");
  await page.getByRole("button", { name: /RUN ORCHESTRATION/ }).click();

  const executionGraph = page.getByTestId("execution-graph");
  await expect(executionGraph).toBeVisible({ timeout: 15000 });
  // Scoped to the graph itself: an unscoped page-wide match also hits the run
  // picker's <option> text (which also carries the run's status in parentheses)
  // — that option is a real match but hidden while the <select> is collapsed.
  await expect(executionGraph.getByText(/COMPLETED|FAILED/).first()).toBeVisible({ timeout: 15000 });

  // Client-side navigation (not page.goto), deliberately: a full page load tears
  // down the WebSocket connection and the in-memory live event-stream store, which
  // has no REST backfill by design — going through the Sidebar link instead
  // preserves the SPA session so the just-completed run's events are still there.
  await page.getByRole("link", { name: "DASHBOARD" }).click();
  await expect(page.getByTestId("activity-feed")).toContainText("ORCHESTRATOR", { timeout: 15000 });
});
