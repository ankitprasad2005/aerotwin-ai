import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type HttpHandler } from "msw";
import { describe, expect, it } from "vitest";
import { api, defaultHandlers, makeDatasets, makeSearch } from "../test/fixtures";
import { server } from "../test/mswServer";
import { renderWithProviders } from "../test/render";
import { DataPage } from "./DataPage";

async function renderLoaded(...overrides: HttpHandler[]) {
  server.use(...overrides, ...defaultHandlers());
  renderWithProviders(<DataPage />);
  await screen.findByTestId("dataset-openflights");
}

describe("DataPage", () => {
  it("shows a loading state, then status, rows and last refresh for each source", async () => {
    server.use(...defaultHandlers());
    renderWithProviders(<DataPage />);
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    await screen.findByTestId("dataset-openflights");
    const flights = screen.getByTestId("dataset-openflights");
    expect(within(flights).getByText("OpenFlights routes")).toBeInTheDocument();
    expect(within(flights).getByText("SUCCESS")).toBeInTheDocument();
    expect(within(flights).getByText("120 rows")).toBeInTheDocument();
    expect(within(screen.getByTestId("dataset-eia_jet_fuel")).getByText("FAILED")).toBeInTheDocument();
    expect(within(screen.getByTestId("dataset-eia_jet_fuel")).getByText("timeout")).toBeInTheDocument();
    expect(within(screen.getByTestId("dataset-fx")).getByText("Never refreshed")).toBeInTheDocument();
    expect(within(screen.getByTestId("dataset-dgca")).getByText("FALLBACK")).toBeInTheDocument();
  });

  it("shows the latest fuel price and exchange rate", async () => {
    await renderLoaded();
    await waitFor(() => expect(within(screen.getByTestId("dataset-eia_jet_fuel")).getByText("$2.31/gal")).toBeInTheDocument());
    await waitFor(() => expect(within(screen.getByTestId("dataset-fx")).getByText("83.42")).toBeInTheDocument());
  });

  it("shows a hint when the price series are empty", async () => {
    await renderLoaded(
      http.get(api("/api/datasets/fuel-prices"), () => HttpResponse.json([])),
      http.get(api("/api/datasets/fx-rates"), () => HttpResponse.json([])),
    );
    await waitFor(() => expect(within(screen.getByTestId("dataset-fx")).getByText("No rates stored yet")).toBeInTheDocument());
    expect(within(screen.getByTestId("dataset-eia_jet_fuel")).getByText("No prices stored yet")).toBeInTheDocument();
  });

  it("refreshes every source and reports the results", async () => {
    let body: unknown;
    await renderLoaded(
      http.post(api("/api/datasets/refresh"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json([
          { source: "openflights", status: "SUCCESS", row_count: 130, error: null, fetched_at: "2026-10-15T10:00:00Z" },
          { source: "fx", status: "FAILED", row_count: 0, error: "boom", fetched_at: "2026-10-15T10:00:00Z" },
        ]);
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Refresh all" }));
    const result = await screen.findByTestId("refresh-result");
    expect(body).toEqual({});
    expect(result).toHaveTextContent("openflights");
    expect(result).toHaveTextContent("130 rows");
    expect(result).toHaveTextContent("boom");
  });

  it("refreshes a single source", async () => {
    let body: unknown;
    await renderLoaded(
      http.post(api("/api/datasets/refresh"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json([
          { source: "fx", status: "SUCCESS", row_count: 5, error: null, fetched_at: "2026-10-15T10:00:00Z" },
        ]);
      }),
    );
    await userEvent.click(within(screen.getByTestId("dataset-fx")).getByRole("button", { name: "Refresh" }));
    await screen.findByTestId("refresh-result");
    expect(body).toEqual({ sources: ["fx"] });
  });

  it("shows an error when the refresh fails", async () => {
    await renderLoaded(http.post(api("/api/datasets/refresh"), () => HttpResponse.json({ detail: "db down" }, { status: 500 })));
    await userEvent.click(screen.getByRole("button", { name: "Refresh all" }));
    expect(await screen.findByText("Refresh failed")).toBeInTheDocument();
    expect(screen.getByText("db down")).toBeInTheDocument();
  });

  it("shows an error when the datasets cannot be loaded", async () => {
    server.use(http.get(api("/api/datasets"), () => HttpResponse.json({ detail: "nope" }, { status: 500 })), ...defaultHandlers());
    renderWithProviders(<DataPage />);
    expect(await screen.findByText("Could not load the datasets")).toBeInTheDocument();
  });

  it("shows an empty state when there are no sources", async () => {
    server.use(http.get(api("/api/datasets"), () => HttpResponse.json([])), ...defaultHandlers());
    renderWithProviders(<DataPage />);
    expect(await screen.findByText("No datasets are registered")).toBeInTheDocument();
  });

  it("only lists the sources the API returns", async () => {
    server.use(http.get(api("/api/datasets"), () => HttpResponse.json(makeDatasets().slice(0, 1))), ...defaultHandlers());
    renderWithProviders(<DataPage />);
    await screen.findByTestId("dataset-openflights");
    expect(screen.queryByTestId("dataset-fx")).not.toBeInTheDocument();
  });

  it("shows the web search status", async () => {
    await renderLoaded();
    const panel = await screen.findByTestId("web-search-status");
    await waitFor(() => expect(panel).toHaveTextContent("Reachable"));
    expect(panel).toHaveTextContent("Enabled");
    expect(panel).toHaveTextContent("Configured");
  });

  it("explains why search is unavailable and disables the query box", async () => {
    await renderLoaded(
      http.get(api("/api/web-search/status"), () => HttpResponse.json({ enabled: true, configured: false, reachable: false })),
    );
    expect(await screen.findByText(/Web search is not available/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
  });

  it("warns when the search engine is unreachable", async () => {
    await renderLoaded(
      http.get(api("/api/web-search/status"), () => HttpResponse.json({ enabled: true, configured: true, reachable: false })),
    );
    expect(await screen.findByText(/cannot be reached/)).toBeInTheDocument();
  });

  it("shows an error state for the status", async () => {
    await renderLoaded(http.get(api("/api/web-search/status"), () => HttpResponse.json({ detail: "x" }, { status: 500 })));
    expect(await screen.findByText("Could not load the web search status")).toBeInTheDocument();
  });

  it("runs a search and lists the results, rendering unsafe links as plain text", async () => {
    let sent: unknown;
    await renderLoaded(
      http.post(api("/api/web-search"), async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(makeSearch({ cached: true, stale: true }));
      }),
    );
    const search = screen.getByRole("button", { name: "Search" });
    expect(search).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Search query"), "  india aviation  ");
    await waitFor(() => expect(search).toBeEnabled());
    await userEvent.click(search);
    const results = await screen.findByTestId("web-search-results");
    expect(sent).toEqual({ query: "india aviation" });
    expect(within(results).getByRole("link", { name: "Result one" })).toHaveAttribute("href", "https://example.com/1");
    expect(within(results).queryByRole("link", { name: "Result two" })).not.toBeInTheDocument();
    expect(within(results).getByText("Result two")).toBeInTheDocument();
    expect(results).toHaveTextContent("cached");
    expect(results).toHaveTextContent("stale");
  });

  it("shows a message when a search returns nothing", async () => {
    await renderLoaded(http.post(api("/api/web-search"), () => HttpResponse.json(makeSearch({ results: [] }))));
    await userEvent.type(screen.getByLabelText("Search query"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No results for this query")).toBeInTheDocument();
  });

  it("shows the search failure", async () => {
    await renderLoaded(http.post(api("/api/web-search"), () => HttpResponse.json({ detail: "Web search failed: boom" }, { status: 502 })));
    await userEvent.type(screen.getByLabelText("Search query"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Search failed")).toBeInTheDocument();
    expect(screen.getByText("Web search failed: boom")).toBeInTheDocument();
  });

  it("limits the query length", async () => {
    await renderLoaded();
    expect(screen.getByLabelText("Search query")).toHaveAttribute("maxlength", "200");
  });

  it("lists cached queries and reruns one", async () => {
    let sent: unknown;
    await renderLoaded(
      http.post(api("/api/web-search"), async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(makeSearch());
      }),
    );
    const cache = await screen.findByTestId("web-search-cache");
    await waitFor(() => expect(cache).toHaveTextContent("india aviation"));
    expect(cache).toHaveTextContent("2 results");
    await userEvent.click(within(cache).getByRole("button", { name: "Run again: india aviation" }));
    await screen.findByTestId("web-search-results");
    expect(sent).toEqual({ query: "india aviation" });
  });

  it("shows an empty cache", async () => {
    await renderLoaded(http.get(api("/api/web-search/cache"), () => HttpResponse.json([])));
    expect(await screen.findByText("No queries cached yet")).toBeInTheDocument();
  });

  it("shows the cache error", async () => {
    await renderLoaded(http.get(api("/api/web-search/cache"), () => HttpResponse.json({ detail: "x" }, { status: 500 })));
    expect(await screen.findByText("Could not load the cached queries")).toBeInTheDocument();
  });
});
