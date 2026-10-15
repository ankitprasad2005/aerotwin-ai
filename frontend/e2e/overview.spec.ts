import { expect, test } from "@playwright/test";

test("the overview loads inside the shell: icon rail, KPI strip and overview heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Key metrics" })).toBeVisible();
  await expect(page.getByTestId("kpi-Runs")).toBeVisible();
});

test("every page is reachable from the icon rail", async ({ page }) => {
  await page.goto("/");
  const pages: [string, string][] = [
    ["Runs", "Runs"],
    ["New run", "New run"],
    ["Data", "Data"],
    ["Weights", "Decision weights"],
    ["Events", "Events"],
    ["Overview", "Overview"],
  ];
  for (const [link, heading] of pages) {
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: link }).click();
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  }
});

test("the legacy /orchestration route redirects to /new and unknown paths to the overview", async ({ page }) => {
  await page.goto("/orchestration");
  await expect(page).toHaveURL(/\/new$/);
  await page.goto("/no/such/page");
  await expect(page).toHaveURL(/\/$/);
});

test("the data page lists the four dataset sources and the web search panel", async ({ page }) => {
  await page.goto("/data");
  for (const source of ["openflights", "eia_jet_fuel", "fx", "dgca"]) {
    await expect(page.getByTestId(`dataset-${source}`)).toBeVisible();
  }
  await expect(page.getByTestId("web-search-status")).toBeVisible();
});
