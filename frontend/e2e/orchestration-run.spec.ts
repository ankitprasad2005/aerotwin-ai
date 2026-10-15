import { expect, test } from "@playwright/test";

test("starting a run shows its decision, evidence and live events", async ({ page }) => {
  // Two full pipelines (the run plus a follow-up prompt), each several real LLM calls.
  test.setTimeout(300000);
  await page.goto("/new");

  await page.getByPlaceholder(/Improve airline profitability/).fill("Improve airline profitability");
  await page.getByRole("button", { name: "Run orchestration" }).click();

  // POST /api/runs blocks until the full pipeline completes, so this wait is where essentially all
  // of the LLM latency lands. The app then opens the finished run.
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+$/, { timeout: 120000 });

  // The decision panel leads the page: verdict, score and the reconciled summary.
  const decision = page.getByTestId("decision-panel");
  await expect(decision).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId("decision-summary-text")).toContainText("frequency");

  // One row per agent that ran.
  await expect(page.getByTestId("agents-table")).toContainText("Network");
  await expect(page.getByTestId("agents-table")).toContainText("Fleet");

  // Execution graph and knowledge graph are tabs of the run.
  await page.getByRole("tab", { name: "Execution graph" }).click();
  await expect(page.getByTestId("execution-graph")).toBeVisible({ timeout: 15000 });
  await page.getByRole("tab", { name: "Knowledge graph" }).click();
  await expect(page.getByTestId("knowledge-graph")).toBeVisible({ timeout: 15000 });

  // Evidence is either listed or explained; the tab must never be blank.
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await expect(page.getByTestId("evidence-list").or(page.getByText("No external evidence was gathered for this prompt"))).toBeVisible({
    timeout: 15000,
  });

  await page.getByRole("tab", { name: "Messages" }).click();
  await expect(page.getByRole("tabpanel")).toBeVisible();

  // A follow-up prompt runs the agents again inside the same run, adding an iteration.
  await page.getByLabel("Follow-up prompt").fill("Now protect load factor on the thin routes");
  await page.getByRole("button", { name: "Add prompt" }).click();
  await expect(page.getByRole("button", { name: "Add prompt" })).toBeVisible({ timeout: 120000 });

  // Client-side navigation (not page.goto), deliberately: a full page load tears down the
  // WebSocket and the in-memory live event-stream store, which has no REST backfill by design.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Overview" }).click();
  await expect(page.getByTestId("activity-feed")).toContainText("ORCHESTRATOR", { timeout: 15000 });
});
