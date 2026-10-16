import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { api, defaultHandlers, LONG_NOTE, makeCatalog, makeExplorerPage } from "../../test/fixtures";
import { server } from "../../test/mswServer";
import { renderWithProviders } from "../../test/render";
import { DataExplorer } from "./DataExplorer";

function Probe() {
  const location = useLocation();
  return <div data-testid="url">{location.search}</div>;
}

function setup(route = "/data?tab=explorer", ...overrides: Parameters<typeof server.use>) {
  server.use(...overrides, ...defaultHandlers());
  return renderWithProviders(
    <>
      <DataExplorer />
      <Probe />
    </>,
    { route },
  );
}

const url = () => new URLSearchParams(screen.getByTestId("url").textContent ?? "");

describe("DataExplorer", () => {
  it("lists categories with dataset counts and the datasets of the first category", async () => {
    setup();
    const categories = await screen.findByRole("navigation", { name: "Categories" });
    expect(within(categories).getByRole("button", { name: /Fuel & prices/ })).toHaveTextContent("2");
    expect(within(categories).getByRole("button", { name: /Safety/ })).toHaveTextContent("1");
    const datasets = screen.getByRole("navigation", { name: "Datasets" });
    expect(within(datasets).getByRole("button", { name: /EIA jet fuel price/ })).toHaveTextContent("120");
    expect(screen.getByText("Pick a dataset")).toBeInTheDocument();
  });

  it("switches category and opens a dataset, writing both to the URL", async () => {
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /Safety/ }));
    expect(url().get("category")).toBe("Safety");
    await userEvent.click(screen.getByRole("button", { name: /Airworthiness directives/ }));
    expect(url().get("dataset")).toBe("airworthiness_directives");
    expect(url().get("category")).toBeNull();
    await screen.findByText("AD 1");
  });

  it("opens the dataset named in the URL with its row count and last refresh", async () => {
    setup("/data?tab=explorer&dataset=fuel_prices");
    await screen.findByText("2.31");
    expect(screen.getByTestId("explorer-meta")).toHaveTextContent("3 rows");
    expect(screen.getByTestId("explorer-meta")).toHaveTextContent("Last refreshed");
    expect(screen.getByRole("columnheader", { name: /USD per gallon/ })).toHaveTextContent("(USD/gal)");
    expect(screen.getByRole("link", { name: "Export CSV" })).toHaveAttribute(
      "href",
      expect.stringContaining("/api/data/fuel_prices/export.csv"),
    );
  });

  it("says no refresh is recorded", async () => {
    setup("/data?tab=explorer&dataset=oil_prices");
    await waitFor(() => expect(screen.getByTestId("explorer-meta")).toHaveTextContent("No refresh recorded"));
  });

  it("requests the page, search, sort and filters from the URL", async () => {
    let requested = "";
    setup(
      "/data?tab=explorer&dataset=fuel_prices&q=jet&sort=usd_per_gallon&order=desc&page=2&f.series=jet",
      http.get(api("/api/data/:key/rows"), ({ request }) => {
        requested = new URL(request.url).search;
        return HttpResponse.json({ ...makeExplorerPage("fuel_prices"), total: 120 });
      }),
    );
    await screen.findByText("2.31");
    const params = new URLSearchParams(requested);
    expect(params.get("limit")).toBe("50");
    expect(params.get("offset")).toBe("50");
    expect(params.get("q")).toBe("jet");
    expect(params.get("sort")).toBe("usd_per_gallon");
    expect(params.get("order")).toBe("desc");
    expect(params.get("filter.series")).toBe("jet");
    expect(screen.getByTestId("explorer-range")).toHaveTextContent("51–100 of 120");
    expect(screen.getByTestId("explorer-filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Filters (1)" })).toBeInTheDocument();
  });

  it("debounces the search into the URL and resets the page", async () => {
    setup("/data?tab=explorer&dataset=fuel_prices&page=2");
    await screen.findByText("2.31");
    await userEvent.type(screen.getByLabelText("Search"), "jet");
    await waitFor(() => expect(url().get("q")).toBe("jet"));
    expect(url().get("page")).toBeNull();
  });

  it("clears the search again", async () => {
    setup("/data?tab=explorer&dataset=fuel_prices&q=jet");
    await screen.findByText("2.31");
    await userEvent.clear(screen.getByLabelText("Search"));
    await waitFor(() => expect(url().get("q")).toBeNull());
  });

  it("cycles the sort ascending, descending, then back to the default", async () => {
    setup("/data?tab=explorer&dataset=fuel_prices");
    await screen.findByText("2.31");
    const header = () => screen.getByRole("columnheader", { name: /USD per gallon/ });
    expect(header()).toHaveAttribute("aria-sort", "none");
    await userEvent.click(within(header()).getByRole("button"));
    await waitFor(() => expect(header()).toHaveAttribute("aria-sort", "ascending"));
    expect(url().get("sort")).toBe("usd_per_gallon");
    await userEvent.click(within(header()).getByRole("button"));
    await waitFor(() => expect(header()).toHaveAttribute("aria-sort", "descending"));
    await userEvent.click(within(header()).getByRole("button"));
    await waitFor(() => expect(header()).toHaveAttribute("aria-sort", "none"));
    expect(url().get("sort")).toBeNull();
    // choosing another column starts ascending
    await userEvent.click(within(screen.getByRole("columnheader", { name: /Series/ })).getByRole("button"));
    await waitFor(() => expect(url().get("sort")).toBe("series"));
  });

  it("filters by column", async () => {
    setup("/data?tab=explorer&dataset=fuel_prices");
    await screen.findByText("2.31");
    expect(screen.queryByTestId("explorer-filters")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    await userEvent.type(screen.getByLabelText("Series", { selector: "input" }), "jet");
    await waitFor(() => expect(url().get("f.series")).toBe("jet"));
    await userEvent.clear(screen.getByLabelText("Series", { selector: "input" }));
    await waitFor(() => expect(url().get("f.series")).toBeNull());
  });

  it("pages forwards and back", async () => {
    setup(
      "/data?tab=explorer&dataset=fuel_prices",
      http.get(api("/api/data/:key/rows"), () => HttpResponse.json({ ...makeExplorerPage("fuel_prices"), total: 120 })),
    );
    await screen.findByText("2.31");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(url().get("page")).toBe("2"));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(screen.getByText("Page 3 of 3")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(url().get("page")).toBeNull());
  });

  it("expands wide and nested values and truncates them inline", async () => {
    setup("/data?tab=explorer&dataset=airworthiness_directives");
    await screen.findByText("AD 1");
    expect(screen.getByTitle(LONG_NOTE)).toBeInTheDocument();
    expect(screen.getByText('["A320","A321"]')).toBeInTheDocument();
    expect(screen.getAllByText("yes").length).toBe(1);
    await userEvent.click(screen.getAllByRole("button", { name: "Expand row" })[0]);
    const detail = screen.getByTestId("row-detail");
    expect(detail).toHaveTextContent(/"A321"/);
    expect(detail).toHaveTextContent(LONG_NOTE);
    await userEvent.click(screen.getByRole("button", { name: "Collapse row" }));
    expect(screen.queryByTestId("row-detail")).not.toBeInTheDocument();
  });

  it("shows an empty dataset and a no-match state", async () => {
    setup(
      "/data?tab=explorer&dataset=fuel_prices",
      http.get(api("/api/data/:key/rows"), () => HttpResponse.json({ total: 0, rows: [] })),
    );
    expect(await screen.findByText("This dataset has no rows yet")).toBeInTheDocument();
  });

  it("explains when a search matches nothing", async () => {
    setup(
      "/data?tab=explorer&dataset=fuel_prices&q=zzz",
      http.get(api("/api/data/:key/rows"), () => HttpResponse.json({ total: 0, rows: [] })),
    );
    expect(await screen.findByText("No rows match")).toBeInTheDocument();
  });

  it("shows a row error with retry", async () => {
    let fail = true;
    setup(
      "/data?tab=explorer&dataset=fuel_prices",
      http.get(api("/api/data/:key/rows"), () =>
        fail ? HttpResponse.json({ detail: "Unknown column: x" }, { status: 422 }) : HttpResponse.json(makeExplorerPage("fuel_prices")),
      ),
    );
    expect(await screen.findByText("Unknown column: x")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("2.31");
  });

  it("shows loading, error and empty states for the catalog", async () => {
    setup("/data?tab=explorer", http.get(api("/api/data/catalog"), () => HttpResponse.json({ detail: "down" }, { status: 500 })));
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("Could not load the data catalog")).toBeInTheDocument();
  });

  it("shows an empty catalog", async () => {
    setup("/data?tab=explorer", http.get(api("/api/data/catalog"), () => HttpResponse.json([])));
    expect(await screen.findByText("No datasets are available")).toBeInTheDocument();
  });

  it("renders a dataset it has never heard of from the catalog alone", async () => {
    const catalog = [
      ...makeCatalog(),
      {
        key: "future_table",
        title: "Future table",
        category: "Brand new",
        description: "Added by a later worker.",
        row_count: 1,
        last_refreshed: null,
        columns: [{ name: "thing", label: "Thing", type: "text" as const, unit: null }],
      },
    ];
    setup(
      "/data?tab=explorer&dataset=future_table",
      http.get(api("/api/data/catalog"), () => HttpResponse.json(catalog)),
      http.get(api("/api/data/future_table/rows"), () => HttpResponse.json({ total: 1, rows: [{ thing: "hello" }] })),
    );
    expect(await screen.findByText("hello")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Brand new/ })).toBeInTheDocument();
  });
});
