import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { defaultHandlers } from "../test/fixtures";
import { server } from "../test/mswServer";
import { renderWithProviders } from "../test/render";
import { DataPage } from "./DataPage";

describe("DataPage tabs", () => {
  it("opens on the Overview tab", async () => {
    server.use(...defaultHandlers());
    renderWithProviders(<DataPage />);
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    await screen.findByTestId("dataset-openflights");
    expect(screen.queryByTestId("data-explorer")).not.toBeInTheDocument();
  });

  it("opens the Explorer from the URL and switches back", async () => {
    server.use(...defaultHandlers());
    renderWithProviders(<DataPage />, { route: "/data?tab=explorer&dataset=fuel_prices" });
    expect(screen.getByRole("tab", { name: "Explorer" })).toHaveAttribute("aria-selected", "true");
    await screen.findByText("2.31");
    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));
    await screen.findByTestId("dataset-openflights");
    expect(screen.queryByTestId("data-explorer")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Explorer" }));
    expect(await screen.findByTestId("data-explorer")).toBeInTheDocument();
    expect(screen.getByText("Pick a dataset")).toBeInTheDocument();
  });
});
