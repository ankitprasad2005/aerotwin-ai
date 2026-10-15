import { expect, test } from "@playwright/test";

test("opening an Agent Inspector populates its tabs from real backend data", async ({ page }) => {
  test.setTimeout(150000);
  await page.goto("/new");
  await page.getByPlaceholder(/Improve airline profitability/).fill("Improve airline profitability");
  await page.getByRole("button", { name: "Run orchestration" }).click();
  // POST /api/runs blocks until the whole pipeline finishes, then the app opens the run.
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+$/, { timeout: 120000 });
  await expect(page.getByTestId("agents-table")).toBeVisible({ timeout: 15000 });

  await page.getByRole("row", { name: "Open Network agent" }).click();
  await expect(page.getByText("AGENT INSPECTOR")).toBeVisible();
  await expect(page.getByTestId("overview-tab")).toBeVisible();

  await page.getByText("CONTEXT", { exact: true }).click();
  await expect(page.getByTestId("context-tab")).toBeVisible();

  await page.getByText("TOOL CALLS", { exact: true }).click();
  await expect(page.getByTestId("tool-call-view")).toBeVisible();
});
