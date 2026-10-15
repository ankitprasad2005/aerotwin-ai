import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defaultHandlers } from "./test/fixtures";
import { server } from "./test/mswServer";
import { useDecisionInspectorStore } from "./stores/decisionInspectorStore";
import { useInspectorStore } from "./stores/inspectorStore";
import { App } from "./App";

class FakeWebSocket {
  onopen: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
  }

  close() {
    // no-op for App-level rendering tests
  }
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  server.use(...defaultHandlers());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderApp(initialPath = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App", () => {
  it("renders the icon rail, KPI strip and overview by default", async () => {
    renderApp("/");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Key metrics" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it.each([
    ["/runs", "Runs"],
    ["/new", "New run"],
    ["/data", "Data"],
    ["/weights", "Decision weights"],
    ["/events", "Events"],
  ])("renders %s", async (path, heading) => {
    renderApp(path);
    expect(await screen.findByRole("heading", { name: heading, level: 1 })).toBeInTheDocument();
  });

  it("renders a run at /runs/:runId", async () => {
    renderApp("/runs/run-1");
    expect(await screen.findByTestId("decision-panel")).toBeInTheDocument();
  });

  it("redirects the legacy /orchestration route to /new", async () => {
    renderApp("/orchestration");
    expect(await screen.findByRole("heading", { name: "New run", level: 1 })).toBeInTheDocument();
  });

  it("redirects unknown paths to the overview", async () => {
    renderApp("/nope/at/all");
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("navigates with the icon rail", async () => {
    renderApp("/");
    await userEvent.click(screen.getByRole("link", { name: "Data" }));
    expect(await screen.findByRole("heading", { name: "Data", level: 1 })).toBeInTheDocument();
  });

  it("closes the agent inspector when navigating to a different page", async () => {
    server.use(
      http.get("http://localhost:8000/api/agent-executions/a1", () =>
        HttpResponse.json({
          id: "a1",
          run_id: "r1",
          agent_type: "NETWORK",
          status: "COMPLETED",
          task: "t",
          elapsed_ms: null,
          recommendation: null,
          total_tokens: null,
          created_at: "2026-09-11T00:00:00Z",
          context_snapshot: null,
          llm_execution: null,
          tool_executions: [],
        }),
      ),
    );
    useInspectorStore.getState().open("a1");
    renderApp("/");
    await waitFor(() => expect(useInspectorStore.getState().agentExecutionId).toBe("a1"));

    await userEvent.click(screen.getByRole("link", { name: "Events" }));
    await waitFor(() => expect(useInspectorStore.getState().agentExecutionId).toBeNull());
    useInspectorStore.getState().close();
  });

  it("closes the decision summary when navigating to a different page", async () => {
    server.use(
      http.get("http://localhost:8000/api/decisions/d1", () =>
        HttpResponse.json({
          id: "d1",
          run_id: "r1",
          summary: "Increase BOM-DEL frequency",
          expected_profit_impact: 85000,
          expected_revenue_impact: 300000,
          expected_cost_impact: 215000,
          confidence: 0.82,
          risks: [],
          constraints_checked: [],
          validation_result: {},
          status: "RECOMMENDED",
          agents_involved: [],
          created_at: "2026-09-11T00:00:00Z",
        }),
      ),
    );
    useDecisionInspectorStore.getState().open("d1");
    renderApp("/");
    await waitFor(() => expect(useDecisionInspectorStore.getState().decisionId).toBe("d1"));

    await userEvent.click(screen.getByRole("link", { name: "Events" }));
    await waitFor(() => expect(useDecisionInspectorStore.getState().decisionId).toBeNull());
    useDecisionInspectorStore.getState().close();
  });
});
