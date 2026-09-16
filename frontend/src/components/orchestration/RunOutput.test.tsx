import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/mswServer";
import { RunOutput } from "./RunOutput";

const NETWORK_EXECUTION = {
  id: "a1",
  run_id: "r1",
  agent_type: "NETWORK",
  status: "COMPLETED",
  task: "Identify profitable route frequency changes.",
  elapsed_ms: 3200,
  total_tokens: 900,
  created_at: "2026-09-11T00:00:00Z",
  recommendation: {
    route: "DEL-BOM",
    action: "INCREASE_FREQUENCY",
    expected_revenue_impact: 28557,
    expected_cost_impact: 9000,
    expected_profit_impact: 19557,
    confidence: 0.95,
    risks: ["fuel price volatility"],
    reasoning: "Weekly demand exceeds current capacity.",
  },
};

const FLEET_EXECUTION = {
  id: "a2",
  run_id: "r1",
  agent_type: "FLEET",
  status: "COMPLETED",
  task: "Assess aircraft availability.",
  elapsed_ms: 2100,
  total_tokens: 600,
  created_at: "2026-09-11T00:00:04Z",
  recommendation: {
    route: "DEL-BOM",
    aircraft_tail_number: "VT-AER2",
    assignment_action: "ASSIGN_ADDITIONAL_AIRCRAFT",
    aircraft_availability: "AVAILABLE",
    expected_cost_impact: 0,
    confidence: 0.95,
    risks: [],
    reasoning: "Aircraft already at the origin.",
  },
};

const DECISION = {
  id: "d1",
  run_id: "r1",
  summary: "Increase DEL-BOM frequency",
  expected_profit_impact: 19557,
  expected_revenue_impact: 28557,
  expected_cost_impact: 9000,
  confidence: 0.95,
  risks: ["fuel price volatility"],
  constraints_checked: ["aircraft_availability_matches_action", "change_has_positive_expected_profit"],
  validation_result: { schema: "PASS", constraints: "PASS", conflicts: [], risk: "LOW" },
  status: "RECOMMENDED",
  agents_involved: ["a1", "a2"],
  created_at: "2026-09-11T00:00:06Z",
};

function runDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: "r1",
    objective: "Improve airline profitability",
    status: "COMPLETED",
    created_at: "2026-09-11T00:00:00Z",
    completed_at: "2026-09-11T00:00:06Z",
    agent_executions: [NETWORK_EXECUTION, FLEET_EXECUTION],
    decision: DECISION,
    iterations: [],
    ...overrides,
  };
}

function renderOutput() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <RunOutput runId="r1" />
    </QueryClientProvider>,
  );
}

describe("RunOutput", () => {
  it("shows every agent's recommendation and the combined decision", async () => {
    server.use(http.get("http://localhost:8000/api/runs/r1", () => HttpResponse.json(runDetail())));
    renderOutput();

    await waitFor(() => expect(screen.getByTestId("run-output")).toBeInTheDocument());
    expect(screen.getAllByTestId("agent-output")).toHaveLength(2);
    expect(screen.getByText("NETWORK AGENT")).toBeInTheDocument();
    expect(screen.getByText("FLEET AGENT")).toBeInTheDocument();
    expect(screen.getByText("INCREASE_FREQUENCY")).toBeInTheDocument();
    expect(screen.getByText("VT-AER2")).toBeInTheDocument();

    const decision = screen.getByTestId("final-decision-output");
    expect(decision).toHaveTextContent("Increase DEL-BOM frequency");
    expect(decision).toHaveTextContent("$19,557");
    expect(decision).toHaveTextContent("95%");
    expect(decision).toHaveTextContent("LOW");
    expect(decision).toHaveTextContent("change_has_positive_expected_profit");
  });

  it("shows conflicts when the decision failed its constraints", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1", () =>
        HttpResponse.json(
          runDetail({
            decision: {
              ...DECISION,
              validation_result: {
                schema: "PASS",
                constraints: "FAIL",
                conflicts: ["Network agent analyzed route MAA-CCU but fleet agent analyzed route DEL-BOM."],
                risk: "HIGH",
              },
            },
          }),
        ),
      ),
    );
    renderOutput();

    await waitFor(() => expect(screen.getByTestId("final-decision-output")).toBeInTheDocument());
    expect(screen.getByText("Conflicts (1)")).toBeInTheDocument();
    expect(screen.getByText(/but fleet agent analyzed route DEL-BOM/)).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("FAIL")).toBeInTheDocument();
  });

  it("falls back to a dash when the validation result has no risk or constraints", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1", () =>
        HttpResponse.json(runDetail({ decision: { ...DECISION, validation_result: {} } })),
      ),
    );
    renderOutput();

    await waitFor(() => expect(screen.getByTestId("final-decision-output")).toBeInTheDocument());
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("says there is no decision when the run failed", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1", () =>
        HttpResponse.json(runDetail({ status: "FAILED", decision: null })),
      ),
    );
    renderOutput();

    await waitFor(() => expect(screen.getByText("[NO DECISION — FAILED]")).toBeInTheDocument());
  });

  it("shows an empty state before any agent has run", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1", () =>
        HttpResponse.json(runDetail({ agent_executions: [], decision: null })),
      ),
    );
    renderOutput();

    await waitFor(() => expect(screen.getByText("[NO AGENT OUTPUT YET]")).toBeInTheDocument());
  });

  it("shows one section per prompt when the run has iterations", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1", () =>
        HttpResponse.json(
          runDetail({
            iterations: [
              {
                id: "i1", run_id: "r1", sequence: 1, objective: "Improve profitability",
                status: "COMPLETED", created_at: "2026-09-11T00:00:00Z", completed_at: "2026-09-11T00:00:06Z",
                agent_executions: [NETWORK_EXECUTION], decision: DECISION,
              },
              {
                id: "i2", run_id: "r1", sequence: 2, objective: "Now protect load factor",
                status: "COMPLETED", created_at: "2026-09-11T00:01:00Z", completed_at: "2026-09-11T00:01:06Z",
                agent_executions: [FLEET_EXECUTION], decision: { ...DECISION, id: "d2", summary: "Decrease MAA-CCU frequency" },
              },
            ],
          }),
        ),
      ),
    );
    renderOutput();

    await waitFor(() => expect(screen.getAllByTestId("run-iteration")).toHaveLength(2));
    expect(screen.getByText("Prompt 1")).toBeInTheDocument();
    expect(screen.getByText("Prompt 2")).toBeInTheDocument();
    expect(screen.getByText("Now protect load factor")).toBeInTheDocument();
    expect(screen.getByText("Decrease MAA-CCU frequency")).toBeInTheDocument();
    // Each prompt shows only its own agents.
    expect(screen.getAllByTestId("agent-output")).toHaveLength(2);
  });

  it("shows a loading state and then an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/r1", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    renderOutput();

    expect(screen.getByText("[LOADING OUTPUT...]")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("[ERROR LOADING OUTPUT]")).toBeInTheDocument());
  });
});
