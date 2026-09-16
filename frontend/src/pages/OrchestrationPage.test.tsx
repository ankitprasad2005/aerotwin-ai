import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { OrchestrationPage } from "./OrchestrationPage";

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

// RunOutput fetches the selected run's detail; these tests exercise the picker and graph, so
// answer with a minimal completed run (RunOutput has its own tests).
beforeEach(() => {
  server.use(
    http.get("http://localhost:8000/api/runs/:runId", ({ params }) =>
      HttpResponse.json({
        id: String(params.runId),
        objective: "x",
        status: "COMPLETED",
        created_at: "2026-09-11T00:00:00Z",
        completed_at: "2026-09-11T00:00:05Z",
        agent_executions: [],
        decision: null,
      }),
    ),
  );
});

describe("OrchestrationPage", () => {
  it("renders the page title, objective form, and run picker", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    renderPage();
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
    expect(screen.getByText("ORCHESTRATION")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /RUN ORCHESTRATION/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("View run")).toBeInTheDocument());
  });

  it("shows a placeholder prompt when no run is selected", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("[SELECT OR START A RUN TO VIEW ITS EXECUTION GRAPH]")).toBeInTheDocument(),
    );
  });

  it("shows the execution graph once a run is selected", async () => {
    server.use(http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])));
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
    server.use(
      http.get("http://localhost:8000/api/runs/new-run-1/graph", () =>
        HttpResponse.json({ nodes: [{ id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED" }], edges: [] }),
      ),
    );
    renderPage();
    await userEvent.type(screen.getByPlaceholderText(/Improve airline profitability/), "x");
    await userEvent.click(screen.getByRole("button", { name: /RUN ORCHESTRATION/ }));
    await waitFor(() => expect(screen.getByTestId("execution-graph")).toBeInTheDocument());
  });

  it("lists fetched runs as options in the run picker", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          {
            id: "1",
            objective: "Improve profitability",
            status: "COMPLETED",
            created_at: "2026-09-11T00:00:00Z",
            completed_at: null,
          },
        ]),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Improve profitability (COMPLETED)")).toBeInTheDocument());
  });

  it("shows the execution graph placeholder for a run selected from the picker", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          {
            id: "1",
            objective: "Improve profitability",
            status: "COMPLETED",
            created_at: "2026-09-11T00:00:00Z",
            completed_at: null,
          },
        ]),
      ),
    );
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({ nodes: [{ id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED" }], edges: [] }),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Improve profitability (COMPLETED)")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("View run"), "1");
    await waitFor(() => expect(screen.getByTestId("execution-graph")).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText("View run"), "");
    expect(screen.getByText("[SELECT OR START A RUN TO VIEW ITS EXECUTION GRAPH]")).toBeInTheDocument();
  });

  it("pre-selects the run given in the ?run= URL query param", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          {
            id: "1",
            objective: "Improve profitability",
            status: "COMPLETED",
            created_at: "2026-09-11T00:00:00Z",
            completed_at: null,
          },
        ]),
      ),
    );
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({ nodes: [{ id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED" }], edges: [] }),
      ),
    );
    renderPage("/orchestration?run=1");
    await waitFor(() => expect(screen.getByTestId("execution-graph")).toBeInTheDocument());
    expect(screen.getByLabelText("View run")).toHaveValue("1");
  });

  it("follows later changes to the ?run= URL query param while mounted", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () => HttpResponse.json([])),
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({ nodes: [{ id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED" }], edges: [] }),
      ),
      http.get("http://localhost:8000/api/runs/2/graph", () =>
        HttpResponse.json({ nodes: [{ id: "agent-2", type: "FLEET_AGENT", status: "COMPLETED" }], edges: [] }),
      ),
    );
    // Same-route navigation (e.g. browser back/forward between two ?run= links) keeps the page mounted.
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
    await waitFor(() => expect(screen.getByText("ORCHESTRATOR")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "GO TO RUN 2" }));

    await waitFor(() => expect(screen.getByText("FLEET_AGENT")).toBeInTheDocument());
    expect(screen.queryByText("ORCHESTRATOR")).not.toBeInTheDocument();
  });
});
