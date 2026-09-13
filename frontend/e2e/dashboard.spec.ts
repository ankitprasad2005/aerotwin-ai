import { expect, test } from "@playwright/test";

test("dashboard loads and shows the control-plane shell", async ({ page }) => {
  await page.goto("/");
  // Scoped to the heading role: "DASHBOARD" also appears as the Sidebar's nav link
  // text, so a plain getByText match is ambiguous (same fix as App.test.tsx).
  await expect(page.getByRole("heading", { name: "DASHBOARD" })).toBeVisible();
  await expect(page.getByText("ACTIVE RUNS")).toBeVisible();
  await expect(page.getByText("+ NEW RUN")).toBeVisible();
});
