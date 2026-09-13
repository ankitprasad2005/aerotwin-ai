import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/mswServer";
import { EventTable } from "./EventTable";

function renderTable(filters = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <EventTable filters={filters} />
    </QueryClientProvider>,
  );
}

describe("EventTable", () => {
  it("shows an empty state when no events match", async () => {
    server.use(http.get("http://localhost:8000/api/events", () => HttpResponse.json([])));
    renderTable();
    await waitFor(() => expect(screen.getByText("[NO EVENTS MATCH]")).toBeInTheDocument());
  });

  it("renders a row per event", async () => {
    server.use(
      http.get("http://localhost:8000/api/events", () =>
        HttpResponse.json([
          {
            id: "1",
            run_id: "r1",
            agent_execution_id: null,
            event_type: "agent.completed",
            severity: "INFO",
            entity_type: null,
            entity_id: null,
            payload: {},
            created_at: "2026-09-11T00:00:00Z",
          },
        ]),
      ),
    );
    renderTable();
    await waitFor(() => expect(screen.getByText("agent.completed")).toBeInTheDocument());
    expect(screen.getByText("r1")).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/events", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    renderTable();
    await waitFor(() => expect(screen.getByText("[ERROR LOADING EVENTS]")).toBeInTheDocument());
  });
});
