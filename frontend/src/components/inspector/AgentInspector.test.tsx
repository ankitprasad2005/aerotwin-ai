import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../test/mswServer";
import { AgentInspector } from "./AgentInspector";

const OTHER_DETAIL_RESPONSE = {
  id: "2",
  run_id: "2",
  agent_type: "FLEET",
  status: "COMPLETED",
  task: "t2",
  elapsed_ms: 1000,
  recommendation: null,
  total_tokens: 50,
  created_at: "2026-09-11T00:00:00Z",
  context_snapshot: null,
  llm_execution: null,
  tool_executions: [],
};

const DETAIL_RESPONSE = {
  id: "1",
  run_id: "2",
  agent_type: "NETWORK",
  status: "COMPLETED",
  task: "t",
  elapsed_ms: 4200,
  recommendation: {
    route: "BOM-DEL",
    action: "INCREASE_FREQUENCY",
    expected_revenue_impact: 26163,
    expected_cost_impact: 9000,
    expected_profit_impact: 17163,
    confidence: 0.9,
    risks: ["crew scheduling"],
    reasoning: "Weekly demand exceeds current capacity.",
  },
  total_tokens: 180,
  created_at: "2026-09-11T00:00:00Z",
  context_snapshot: {
    id: "3",
    agent_execution_id: "1",
    payload: { objective: "x" },
    created_at: "2026-09-11T00:00:00Z",
  },
  llm_execution: null,
  tool_executions: [],
};

function renderInspector(agentExecutionId: string | null, onClose = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <AgentInspector agentExecutionId={agentExecutionId} onClose={onClose} />
    </QueryClientProvider>,
  );
  return {
    onClose,
    rerenderWith: (nextAgentExecutionId: string | null) =>
      utils.rerender(
        <QueryClientProvider client={queryClient}>
          <AgentInspector agentExecutionId={nextAgentExecutionId} onClose={onClose} />
        </QueryClientProvider>,
      ),
  };
}

describe("AgentInspector", () => {
  it("renders nothing when agentExecutionId is null", () => {
    renderInspector(null);
    expect(screen.queryByText("AGENT INSPECTOR")).not.toBeInTheDocument();
  });

  it("shows the Overview tab by default once data loads", async () => {
    server.use(http.get("http://localhost:8000/api/agent-executions/1", () => HttpResponse.json(DETAIL_RESPONSE)));
    renderInspector("1");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());
  });

  it("switches to the Context tab when clicked", async () => {
    server.use(http.get("http://localhost:8000/api/agent-executions/1", () => HttpResponse.json(DETAIL_RESPONSE)));
    renderInspector("1");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());
    await userEvent.click(screen.getByText("CONTEXT"));
    expect(screen.getByTestId("context-tab")).toBeInTheDocument();
  });

  it("resets to the Overview tab when reopened for a different agent execution", async () => {
    server.use(http.get("http://localhost:8000/api/agent-executions/1", () => HttpResponse.json(DETAIL_RESPONSE)));
    server.use(
      http.get("http://localhost:8000/api/agent-executions/2", () => HttpResponse.json(OTHER_DETAIL_RESPONSE)),
    );
    const { rerenderWith } = renderInspector("1");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());
    await userEvent.click(screen.getByText("CONTEXT"));
    expect(screen.getByTestId("context-tab")).toBeInTheDocument();

    rerenderWith("2");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());
  });

  it("shows an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/agent-executions/1", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderInspector("1");
    await waitFor(() => expect(screen.getByText("[ERROR LOADING AGENT]")).toBeInTheDocument());
  });

  it("switches to the LLM Call tab when clicked", async () => {
    server.use(http.get("http://localhost:8000/api/agent-executions/1", () => HttpResponse.json(DETAIL_RESPONSE)));
    renderInspector("1");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());
    await userEvent.click(screen.getByText("LLM CALL"));
    expect(screen.getByText("[NO LLM CALL YET]")).toBeInTheDocument();
  });

  it("switches to the Tool Calls tab when clicked", async () => {
    server.use(http.get("http://localhost:8000/api/agent-executions/1", () => HttpResponse.json(DETAIL_RESPONSE)));
    renderInspector("1");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());
    await userEvent.click(screen.getByText("TOOL CALLS"));
    expect(screen.getByText("[NO TOOL CALLS YET]")).toBeInTheDocument();
  });

  it("switches to the Timeline tab when clicked", async () => {
    server.use(http.get("http://localhost:8000/api/agent-executions/1", () => HttpResponse.json(DETAIL_RESPONSE)));
    server.use(http.get("http://localhost:8000/api/events", () => HttpResponse.json([])));
    renderInspector("1");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());
    await userEvent.click(screen.getByText("TIMELINE"));
    await waitFor(() => expect(screen.getByText("[NO TIMELINE EVENTS]")).toBeInTheDocument());
  });
});

describe("AgentInspector OUTPUT tab", () => {
  it("shows the agent's structured recommendation", async () => {
    server.use(http.get("http://localhost:8000/api/agent-executions/1", () => HttpResponse.json(DETAIL_RESPONSE)));
    renderInspector("1");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());

    await userEvent.click(screen.getByText("OUTPUT"));

    expect(screen.getByTestId("recommendation-view")).toBeInTheDocument();
    expect(screen.getByText("INCREASE_FREQUENCY")).toBeInTheDocument();
    expect(screen.getByText("$17,163")).toBeInTheDocument();
    expect(screen.getByText("90%")).toBeInTheDocument();
    expect(screen.getByText("Weekly demand exceeds current capacity.")).toBeInTheDocument();
  });

  it("says so when the agent has no recommendation yet", async () => {
    server.use(
      http.get("http://localhost:8000/api/agent-executions/2", () => HttpResponse.json(OTHER_DETAIL_RESPONSE)),
    );
    renderInspector("2");
    await waitFor(() => expect(screen.getByTestId("overview-tab")).toBeInTheDocument());

    await userEvent.click(screen.getByText("OUTPUT"));

    expect(screen.getByText("[NO RECOMMENDATION YET]")).toBeInTheDocument();
  });
});
