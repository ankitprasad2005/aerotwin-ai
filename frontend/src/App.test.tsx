import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "./test/mswServer";
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
  it("renders the sidebar, header, and dashboard route by default", () => {
    renderApp("/");
    expect(screen.getByRole("heading", { name: "DASHBOARD" })).toBeInTheDocument();
    expect(screen.getByText("+ NEW RUN")).toBeInTheDocument();
    expect(screen.getByTestId("page-content")).toHaveTextContent("DASHBOARD");
  });

  it("renders the orchestration page at /orchestration", () => {
    renderApp("/orchestration");
    expect(screen.getByTestId("page-content")).toHaveTextContent("ORCHESTRATION");
  });

  it("renders the events page at /events", () => {
    renderApp("/events");
    expect(screen.getByTestId("page-content")).toHaveTextContent("EVENTS");
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

    await userEvent.click(screen.getByText("EVENTS"));
    await waitFor(() => expect(useInspectorStore.getState().agentExecutionId).toBeNull());
    useInspectorStore.getState().close();
  });
});
