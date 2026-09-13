import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../test/mswServer";
import { DecisionSummary } from "./DecisionSummary";

const DECISION_RESPONSE = {
  id: "6",
  run_id: "2",
  summary: "Increase BOM-DEL frequency",
  expected_profit_impact: 85000,
  expected_revenue_impact: 300000,
  expected_cost_impact: 215000,
  confidence: 0.82,
  risks: ["fuel price volatility"],
  constraints_checked: ["aircraft_availability_matches_action"],
  validation_result: { schema: "PASS", constraints: "PASS", conflicts: [], risk: "LOW" },
  status: "RECOMMENDED",
  agents_involved: ["1"],
  created_at: "2026-09-11T00:00:00Z",
};

function renderSummary(decisionId: string | null, onClose = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <DecisionSummary decisionId={decisionId} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose };
}

describe("DecisionSummary", () => {
  it("renders nothing when decisionId is null", () => {
    renderSummary(null);
    expect(screen.queryByText("DECISION SUMMARY")).not.toBeInTheDocument();
  });

  it("shows the summary, confidence, and profit/revenue/cost impact once data loads", async () => {
    server.use(http.get("http://localhost:8000/api/decisions/6", () => HttpResponse.json(DECISION_RESPONSE)));
    renderSummary("6");
    await waitFor(() => expect(screen.getByTestId("decision-summary")).toBeInTheDocument());
    expect(screen.getByText("Increase BOM-DEL frequency")).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("$85,000")).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/decisions/6", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderSummary("6");
    await waitFor(() => expect(screen.getByText("[ERROR LOADING DECISION]")).toBeInTheDocument());
  });
});
