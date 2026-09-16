import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../../test/mswServer";
import { useDecisionInspectorStore } from "../../stores/decisionInspectorStore";
import { useInspectorStore } from "../../stores/inspectorStore";
import { KnowledgeGraph } from "./KnowledgeGraph";

const GRAPH = {
  nodes: [
    { id: "agent-a1", type: "AGENT", label: "NETWORK AGENT", detail: "COMPLETED", agent_execution_id: "a1" },
    { id: "route-DEL-BOM", type: "ROUTE", label: "DEL-BOM", detail: "current_frequency=7" },
    { id: "aircraft-VT-AER2", type: "AIRCRAFT", label: "VT-AER2", detail: "status=AVAILABLE" },
    { id: "constraint-0", type: "CONSTRAINT", label: "CONSTRAINT 1", detail: "Keep load factor above 50%" },
    { id: "decision-d1", type: "DECISION", label: "Increase DEL-BOM frequency", detail: "risk=LOW", decision_id: "d1" },
  ],
  edges: [
    { source: "agent-a1", target: "route-DEL-BOM", label: "knows" },
    { source: "agent-a1", target: "decision-d1", label: "feeds" },
  ],
};

beforeEach(() => {
  useInspectorStore.getState().close();
  useDecisionInspectorStore.getState().close();
});

function renderGraph() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <KnowledgeGraph runId="r1" />
    </QueryClientProvider>,
  );
}

describe("KnowledgeGraph", () => {
  it("shows a loading state first", () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1/knowledge-graph", async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json(GRAPH);
      }),
    );
    renderGraph();
    expect(screen.getByText("[LOADING KNOWLEDGE GRAPH...]")).toBeInTheDocument();
  });

  it("renders a node per piece of knowledge, labelled by kind", async () => {
    server.use(http.get("http://localhost:8000/api/runs/r1/knowledge-graph", () => HttpResponse.json(GRAPH)));
    renderGraph();

    await waitFor(() => expect(screen.getByTestId("knowledge-graph")).toBeInTheDocument());
    expect(screen.getByText("NETWORK AGENT")).toBeInTheDocument();
    expect(screen.getByText("DEL-BOM")).toBeInTheDocument();
    expect(screen.getByText("VT-AER2")).toBeInTheDocument();
    expect(screen.getByText("CONSTRAINT 1")).toBeInTheDocument();
    expect(screen.getByText("Increase DEL-BOM frequency")).toBeInTheDocument();
    expect(screen.getByText("current_frequency=7")).toBeInTheDocument();
    expect(screen.getAllByTestId("knowledge-node")).toHaveLength(5);
  });

  it("opens the agent inspector from an agent node", async () => {
    server.use(http.get("http://localhost:8000/api/runs/r1/knowledge-graph", () => HttpResponse.json(GRAPH)));
    renderGraph();
    await waitFor(() => expect(screen.getByText("NETWORK AGENT")).toBeInTheDocument());

    // fireEvent (not userEvent): userEvent's pointer sequence trips @xyflow/react's d3-drag
    // listener under jsdom, same as in ExecutionGraph's tests.
    fireEvent.click(screen.getByText("NETWORK AGENT"));

    expect(useInspectorStore.getState().agentExecutionId).toBe("a1");
  });

  it("opens the decision summary from a decision node", async () => {
    server.use(http.get("http://localhost:8000/api/runs/r1/knowledge-graph", () => HttpResponse.json(GRAPH)));
    renderGraph();
    await waitFor(() => expect(screen.getByText("Increase DEL-BOM frequency")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Increase DEL-BOM frequency"));

    expect(useDecisionInspectorStore.getState().decisionId).toBe("d1");
  });

  it("says so when the run has no agent knowledge yet", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1/knowledge-graph", () =>
        HttpResponse.json({ nodes: [], edges: [] }),
      ),
    );
    renderGraph();
    await waitFor(() => expect(screen.getByText("[NO AGENT KNOWLEDGE YET]")).toBeInTheDocument());
  });

  it("shows an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1/knowledge-graph", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderGraph();
    await waitFor(() => expect(screen.getByText("[ERROR LOADING KNOWLEDGE GRAPH]")).toBeInTheDocument());
  });
});
