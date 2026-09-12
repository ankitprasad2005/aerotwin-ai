import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { useEventStreamStore } from "../stores/eventStreamStore";
import { DashboardPage } from "./DashboardPage";

beforeEach(() => {
  useEventStreamStore.getState().clear();
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  it("renders the page title, page-content testid, and stat tiles", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    renderPage();
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
    expect(screen.getByText("DASHBOARD")).toBeInTheDocument();
    expect(screen.getByTestId("stat-tile-ACTIVE RUNS")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("[NO RUNS YET]")).toBeInTheDocument());
  });

  it("counts a RUNNING run from the live event store into ACTIVE RUNS", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: "r1",
      agent_execution_id: null,
      event_type: "orchestration.started",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T00:00:00Z",
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("stat-tile-ACTIVE RUNS")).toHaveTextContent("1"));
  });

  it("counts FAILED runs from the fetched run list", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          { id: "1", objective: "x", status: "FAILED", created_at: "2026-09-11T00:00:00Z", completed_at: null },
        ]),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByTestId("stat-tile-FAILED")).toHaveTextContent("1"));
  });
});
