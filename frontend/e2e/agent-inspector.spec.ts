import { expect, test } from "@playwright/test";

test("opening an Agent Inspector populates its tabs from real backend data", async ({ page }) => {
  await page.goto("/orchestration");
  await page.getByPlaceholder(/Improve airline profitability/).fill("Improve airline profitability");
  await page.getByRole("button", { name: /RUN ORCHESTRATION/ }).click();
  await expect(page.getByTestId("run-output")).toBeVisible({ timeout: 60000 });
  await page.getByRole("tab", { name: "EXECUTION GRAPH" }).click();
  await expect(page.getByTestId("execution-graph")).toBeVisible({ timeout: 15000 });

  await page.getByText("NETWORK_AGENT").click();
  await expect(page.getByText("AGENT INSPECTOR")).toBeVisible();
  await expect(page.getByTestId("overview-tab")).toBeVisible();

  await page.getByText("CONTEXT", { exact: true }).click();
  await expect(page.getByTestId("context-tab")).toBeVisible();

  await page.getByText("TOOL CALLS", { exact: true }).click();
  await expect(page.getByTestId("tool-call-view")).toBeVisible();
});
