import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../../test/mswServer";
import { useDecisionInspectorStore } from "../../stores/decisionInspectorStore";
import { useEventStreamStore } from "../../stores/eventStreamStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { ExecutionGraph } from "./ExecutionGraph";

beforeEach(() => {
  useEventStreamStore.getState().clear();
  useInspectorStore.getState().close();
  useDecisionInspectorStore.getState().close();
});

function renderGraph(runId: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ExecutionGraph runId={runId} />
    </QueryClientProvider>,
  );
}

describe("ExecutionGraph", () => {
  it("shows a loading state before the graph loads", () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json({ nodes: [], edges: [] });
      }),
    );
    renderGraph("1");
    expect(screen.getByText("[LOADING GRAPH...]")).toBeInTheDocument();
  });

  it("renders a node for each graph node returned by the backend", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({
          nodes: [
            { id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED" },
            { id: "agent-1", type: "NETWORK_AGENT", status: "COMPLETED", agent_execution_id: "a1" },
          ],
          edges: [{ source: "orchestrator", target: "agent-1" }],
        }),
      ),
    );
    renderGraph("1");
    await waitFor(() => expect(screen.getByText("ORCHESTRATOR")).toBeInTheDocument());
    expect(screen.getByText("NETWORK_AGENT")).toBeInTheDocument();
  });

  it("overrides a node's status with the live status from the event store when available", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({
          nodes: [{ id: "agent-1", type: "NETWORK_AGENT", status: "WAITING", agent_execution_id: "a1" }],
          edges: [],
        }),
      ),
    );
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: "1",
      agent_execution_id: "a1",
      event_type: "agent.started",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T00:00:00Z",
    });
    renderGraph("1");
    await waitFor(() => expect(screen.getByText("NETWORK_AGENT")).toBeInTheDocument());
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("overrides the orchestrator node's status with the live run status from the event store", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({
          nodes: [{ id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED" }],
          edges: [],
        }),
      ),
    );
    useEventStreamStore.getState().addEvent({
      id: "1",
      run_id: "1",
      agent_execution_id: null,
      event_type: "orchestration.started",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: {},
      created_at: "2026-09-11T00:00:00Z",
    });
    renderGraph("1");
    await waitFor(() => expect(screen.getByText("ORCHESTRATOR")).toBeInTheDocument());
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("shows an error state when the graph request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderGraph("1");
    await waitFor(() => expect(screen.getByText("[ERROR LOADING GRAPH]")).toBeInTheDocument());
  });

  it("opens the inspector when a node with an agent_execution_id is clicked", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({
          nodes: [{ id: "agent-1", type: "NETWORK_AGENT", status: "COMPLETED", agent_execution_id: "a1" }],
          edges: [],
        }),
      ),
    );
    renderGraph("1");
    await waitFor(() => expect(screen.getByText("NETWORK_AGENT")).toBeInTheDocument());
    // fireEvent.click (not userEvent.click) deliberately: userEvent's full
    // pointer-down/up sequence trips @xyflow/react's internal d3-drag mousedown
    // listener under jsdom (event.view comes back null there), crashing the test
    // with an unhandled error even though the click handler itself fires correctly.
    fireEvent.click(screen.getByText("NETWORK_AGENT"));
    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
  });

  it("opens the decision summary when a node with a decision_id is clicked", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({
          nodes: [{ id: "final_decision", type: "FINAL_DECISION", status: "COMPLETED", decision_id: "d1" }],
          edges: [],
        }),
      ),
    );
    renderGraph("1");
    await waitFor(() => expect(screen.getByText("FINAL_DECISION")).toBeInTheDocument());
    fireEvent.click(screen.getByText("FINAL_DECISION"));
    expect(useDecisionInspectorStore.getState().decisionId).toBe("d1");
  });
});
