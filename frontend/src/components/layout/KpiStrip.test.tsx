import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { api, defaultHandlers, makeStats } from "../../test/fixtures";
import { server } from "../../test/mswServer";
import { useConnectionStore } from "../../stores/connectionStore";
import { useDebugStore } from "../../stores/debugStore";
import { KpiStrip } from "./KpiStrip";

beforeEach(() => {
  useConnectionStore.setState({ status: "open" });
  useDebugStore.setState({ enabled: false });
});

function renderStrip() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <KpiStrip />
    </QueryClientProvider>,
  );
}

describe("KpiStrip", () => {
  it("shows the headline metrics from /api/stats", async () => {
    server.use(...defaultHandlers());
    renderStrip();
    await waitFor(() => expect(screen.getByTestId("kpi-Runs")).toHaveTextContent("12"));
    expect(screen.getByTestId("kpi-Failed")).toHaveTextContent("2");
    expect(screen.getByTestId("kpi-p95 time")).toHaveTextContent("48.5 s");
    expect(screen.getByTestId("kpi-Tokens 24h")).toHaveTextContent("42.0K");
    expect(screen.getByTestId("kpi-Jet fuel")).toHaveTextContent("$2.31/gal");
    expect(screen.getByTestId("kpi-USD/INR")).toHaveTextContent("83.42");
    expect(screen.getByRole("img", { name: "Runs per day, last 14 days" })).toBeInTheDocument();
  });

  it("shows dashes while stats are loading", () => {
    server.use(...defaultHandlers());
    renderStrip();
    expect(screen.getByTestId("kpi-Runs")).toHaveTextContent("—");
    expect(screen.getByTestId("kpi-p95 time")).toHaveTextContent("—");
  });

  it("copes with no p95, no fuel and no exchange rate", async () => {
    server.use(
      http.get(api("/api/stats"), () =>
        HttpResponse.json(
          makeStats({ p95_run_duration_ms: null, latest_fuel_price: null, latest_usd_inr: null, runs_failed: 0, runs_per_day: [], tokens_per_day: [] }),
        ),
      ),
      http.get(api("/api/datasets/fuel-prices"), () => HttpResponse.json([])),
      ...defaultHandlers(),
    );
    renderStrip();
    await waitFor(() => expect(screen.getByTestId("kpi-Runs")).toHaveTextContent("12"));
    expect(screen.getByTestId("kpi-p95 time")).toHaveTextContent("—");
    expect(screen.getByTestId("kpi-Jet fuel")).toHaveTextContent("—");
    expect(screen.getByTestId("kpi-USD/INR")).toHaveTextContent("—");
    expect(screen.getByTestId("kpi-Failed").querySelector(".text-bad")).toBeNull();
    expect(screen.getByRole("img", { name: "Jet fuel price, last 30 days: no data" })).toBeInTheDocument();
    await userEvent.hover(screen.getByTestId("kpi-Jet fuel"));
    expect(screen.getByRole("tooltip")).toHaveTextContent("No fuel price yet");
    await userEvent.unhover(screen.getByTestId("kpi-Jet fuel"));
    await userEvent.hover(screen.getByTestId("kpi-USD/INR"));
    expect(screen.getByRole("tooltip")).toHaveTextContent("No exchange rate yet");
  });

  it("offers a retry when stats fail to load", async () => {
    let calls = 0;
    server.use(
      http.get(api("/api/stats"), () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: "down" }, { status: 500 }) : HttpResponse.json(makeStats());
      }),
      ...defaultHandlers(),
    );
    renderStrip();
    const retry = await screen.findByRole("button", { name: /Stats unavailable/ });
    await userEvent.click(retry);
    await waitFor(() => expect(screen.getByTestId("kpi-Runs")).toHaveTextContent("12"));
    expect(screen.queryByRole("button", { name: /Stats unavailable/ })).not.toBeInTheDocument();
  });

  it("highlights failed runs in red", async () => {
    server.use(...defaultHandlers());
    renderStrip();
    await waitFor(() => expect(screen.getByTestId("kpi-Failed")).toHaveTextContent("2"));
    expect(screen.getByTestId("kpi-Failed").querySelector(".text-bad")).not.toBeNull();
  });

  it.each([
    ["open", "Live"],
    ["connecting", "Connecting"],
    ["closed", "Disconnected"],
  ] as const)("shows the WebSocket status %s", (status, label) => {
    server.use(...defaultHandlers());
    useConnectionStore.setState({ status });
    renderStrip();
    expect(screen.getByRole("status", { name: `Event stream: ${label}` })).toBeInTheDocument();
  });

  it("explains a disconnected stream in its tooltip", async () => {
    server.use(...defaultHandlers());
    useConnectionStore.setState({ status: "closed" });
    renderStrip();
    await userEvent.hover(screen.getByRole("status", { name: /Disconnected/ }));
    expect(screen.getByRole("tooltip")).toHaveTextContent(/paused/);
  });

  it("toggles debug mode", async () => {
    server.use(...defaultHandlers());
    renderStrip();
    const toggle = screen.getByRole("button", { name: /Debug off/ });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(toggle);
    expect(useDebugStore.getState().enabled).toBe(true);
    expect(screen.getByRole("button", { name: /Debug on/ })).toHaveAttribute("aria-pressed", "true");
  });
});
