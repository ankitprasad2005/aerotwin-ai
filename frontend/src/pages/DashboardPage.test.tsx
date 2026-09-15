import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
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
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
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

  it("counts a RUNNING run from the fetched list even with no matching live event", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          { id: "pre-existing", objective: "x", status: "RUNNING", created_at: "2026-09-11T00:00:00Z", completed_at: null },
        ]),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByTestId("stat-tile-ACTIVE RUNS")).toHaveTextContent("1"));
  });

  it("does not double-count a run that is RUNNING in both the live store and the fetched list", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          { id: "r1", objective: "x", status: "RUNNING", created_at: "2026-09-11T00:00:00Z", completed_at: null },
        ]),
      ),
    );
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

  it("counts agent executions in a live-work status into AGENTS RUNNING NOW", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: null,
      agent_execution_id: "agent-1",
      event_type: "llm.request",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T00:00:00Z",
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("stat-tile-AGENTS RUNNING NOW")).toHaveTextContent("1"));
  });

  it("does not count a COMPLETED agent execution into AGENTS RUNNING NOW", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: null,
      agent_execution_id: "agent-1",
      event_type: "agent.completed",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T00:00:00Z",
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("stat-tile-AGENTS RUNNING NOW")).toHaveTextContent("0"));
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

  it("lets a terminal status from the fetched list override a stale live RUNNING status", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          {
            id: "r1",
            objective: "x",
            status: "COMPLETED",
            created_at: "2026-09-11T00:00:00Z",
            completed_at: "2026-09-11T00:01:00Z",
          },
        ]),
      ),
    );
    // orchestration.started was seen live, but the completion event was missed.
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
    await waitFor(() => expect(screen.getByText("x")).toBeInTheDocument());
    expect(screen.getByTestId("stat-tile-ACTIVE RUNS")).toHaveTextContent("0");
  });

  it("keeps a live terminal status over a fetched RUNNING status", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          { id: "r1", objective: "x", status: "RUNNING", created_at: "2026-09-11T00:00:00Z", completed_at: null },
        ]),
      ),
    );
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: "r1",
      agent_execution_id: null,
      event_type: "orchestration.completed",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T00:01:00Z",
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("x")).toBeInTheDocument());
    expect(screen.getByTestId("stat-tile-ACTIVE RUNS")).toHaveTextContent("0");
  });

  it("counts only runs completed today into DECISIONS TODAY", async () => {
    const now = new Date().toISOString();
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          { id: "today", objective: "today", status: "COMPLETED", created_at: now, completed_at: now },
          {
            id: "old",
            objective: "old",
            status: "COMPLETED",
            created_at: "2020-01-01T00:00:00Z",
            completed_at: "2020-01-01T00:01:00Z",
          },
          { id: "no-end", objective: "no-end", status: "COMPLETED", created_at: now, completed_at: null },
          { id: "failed", objective: "failed", status: "FAILED", created_at: now, completed_at: now },
        ]),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("today")).toBeInTheDocument());
    expect(screen.getByTestId("stat-tile-DECISIONS TODAY")).toHaveTextContent("1");
  });
});
