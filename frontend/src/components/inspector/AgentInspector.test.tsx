import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../test/mswServer";
import { AgentInspector } from "./AgentInspector";

const DETAIL_RESPONSE = {
  id: "1",
  run_id: "2",
  agent_type: "NETWORK",
  status: "COMPLETED",
  task: "t",
  elapsed_ms: 4200,
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
  render(
    <QueryClientProvider client={queryClient}>
      <AgentInspector agentExecutionId={agentExecutionId} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose };
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

  it("shows an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/agent-executions/1", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderInspector("1");
    await waitFor(() => expect(screen.getByText("[ERROR LOADING AGENT]")).toBeInTheDocument());
  });
});
