import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { OrchestrationPage } from "./OrchestrationPage";

const RUNS = [
  {
    id: "1",
    objective: "Improve profitability",
    status: "COMPLETED",
    created_at: "2026-09-11T00:00:00Z",
    completed_at: "2026-09-11T00:00:06Z",
  },
  {
    id: "2",
    objective: "Cut costs on thin routes",
    status: "FAILED",
    created_at: "2026-09-11T00:10:00Z",
    completed_at: "2026-09-11T00:10:04Z",
  },
];

function runDetail(runId: string) {
  return {
    id: runId,
    objective: "Improve profitability",
    status: "COMPLETED",
    created_at: "2026-09-11T00:00:00Z",
    completed_at: "2026-09-11T00:00:06Z",
    agent_executions: [],
    decision: null,
    iterations: [],
  };
}

beforeEach(() => {
  server.use(
    http.get("http://localhost:8000/api/runs", () => HttpResponse.json(RUNS)),
    http.get("http://localhost:8000/api/runs/:runId", ({ params }) =>
      HttpResponse.json(runDetail(String(params.runId))),
    ),
    http.get("http://localhost:8000/api/runs/:runId/graph", () =>
      HttpResponse.json({
        nodes: [{ id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED", iteration: null }],
        edges: [],
      }),
    ),
    http.get("http://localhost:8000/api/runs/:runId/knowledge-graph", () =>
      HttpResponse.json({
        nodes: [
          { id: "route-DEL-BOM", type: "ROUTE", label: "DEL-BOM", detail: "current_frequency=7" },
        ],
        edges: [],
      }),
    ),
  );
});

function renderPage(initialPath = "/orchestration") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <OrchestrationPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OrchestrationPage", () => {
  it("lists every run alongside the objective form", async () => {
    renderPage();
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /RUN ORCHESTRATION/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("run-list")).toBeInTheDocument());
    expect(screen.getByText("Improve profitability")).toBeInTheDocument();
    expect(screen.getByText("Cut costs on thin routes")).toBeInTheDocument();
  });

  it("shows a placeholder until a run is selected", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("[SELECT OR START A RUN TO VIEW ITS EXECUTION GRAPH]")).toBeInTheDocument(),
    );
  });

  it("opens the selected run on its output tab", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Cut costs on thin routes")).toBeInTheDocument());

    await userEvent.click(screen.getByText("Cut costs on thin routes"));

    await waitFor(() => expect(screen.getByTestId("run-output")).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "OUTPUT" })).toHaveAttribute("aria-selected", "true");
  });

  it("switches between the execution graph, knowledge graph and prompt tabs", async () => {
    renderPage("/orchestration?run=1");
    await waitFor(() => expect(screen.getByTestId("run-output")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("tab", { name: "EXECUTION GRAPH" }));
    await waitFor(() => expect(screen.getByTestId("execution-graph")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("tab", { name: "KNOWLEDGE GRAPH" }));
    await waitFor(() => expect(screen.getByTestId("knowledge-graph")).toBeInTheDocument());
    expect(screen.getByText("DEL-BOM")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "PROMPT" }));
    expect(screen.getByTestId("prompt-panel")).toBeInTheDocument();
  });

  it("pre-selects the run given in the ?run= URL query param", async () => {
    renderPage("/orchestration?run=2");
    await waitFor(() => expect(screen.getByTestId("run-output")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Cut costs on thin routes/ })).toHaveAttribute("aria-current", "true");
  });

  it("follows later changes to the ?run= URL query param while mounted", async () => {
    // Same-route navigation (e.g. browser back/forward between run links) keeps the page mounted.
    function GoToRun2() {
      const navigate = useNavigate();
      return (
        <button type="button" onClick={() => navigate("/orchestration?run=2")}>
          GO TO RUN 2
        </button>
      );
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/orchestration?run=1"]}>
          <GoToRun2 />
          <OrchestrationPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Improve profitability/ })).toHaveAttribute("aria-current", "true"),
    );

    await userEvent.click(screen.getByRole("button", { name: "GO TO RUN 2" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Cut costs on thin routes/ })).toHaveAttribute("aria-current", "true"),
    );
  });

  it("selects a newly created run", async () => {
    server.use(
      http.post("http://localhost:8000/api/runs", () =>
        HttpResponse.json({
          id: "new-run-1",
          objective: "x",
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: "2026-09-11T00:00:05Z",
        }),
      ),
    );
    renderPage();
    await userEvent.type(screen.getByPlaceholderText(/Improve airline profitability/), "x");
    await userEvent.click(screen.getByRole("button", { name: /RUN ORCHESTRATION/ }));

    await waitFor(() => expect(screen.getByTestId("run-output")).toBeInTheDocument());
  });
});
