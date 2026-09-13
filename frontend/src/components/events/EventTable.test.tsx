import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/mswServer";
import { useDebugStore } from "../../stores/debugStore";
import { useInspectorStore } from "../../stores/inspectorStore";
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

  it("opens the inspector when a row with an agent_execution_id is clicked", async () => {
    server.use(
      http.get("http://localhost:8000/api/events", () =>
        HttpResponse.json([
          {
            id: "1",
            run_id: "r1",
            agent_execution_id: "a1",
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
    await userEvent.click(screen.getByText("agent.completed"));
    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
  });

  it("shows a PAYLOAD column when debug mode is enabled", async () => {
    useDebugStore.setState({ enabled: true });
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
            payload: { foo: "bar" },
            created_at: "2026-09-11T00:00:00Z",
          },
        ]),
      ),
    );
    renderTable();
    await waitFor(() => expect(screen.getByText("PAYLOAD")).toBeInTheDocument());
    expect(screen.getByText(/"foo":"bar"/)).toBeInTheDocument();
    useDebugStore.setState({ enabled: false });
  });
});
