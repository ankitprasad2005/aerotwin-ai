import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api, defaultHandlers, makeDecision, makeWeights } from "../../test/fixtures";
import { server } from "../../test/mswServer";
import { renderWithProviders } from "../../test/render";
import { DecisionPanel } from "./DecisionPanel";

describe("DecisionPanel", () => {
  it("shows verdict, score, money, factor breakdown, warnings and conflicts", async () => {
    server.use(
      http.get(api("/api/decision-weights"), () =>
        HttpResponse.json({ ...makeWeights(), thresholds: { recommend: 80, review: 30 } }),
      ),
      ...defaultHandlers(),
    );
    const decision = makeDecision({
      validation_result: {
        ...makeDecision().validation_result,
        conflicts: ["Fleet assigns grounded aircraft VT-ABC"],
        constraints: "FAIL",
        risk: "HIGH",
        verdict: "REJECT",
        score: 33,
      },
    });
    renderWithProviders(<DecisionPanel decision={decision} runStatus="COMPLETED" />);
    expect(screen.getByText("Reject")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Decision score: 33 out of 100" })).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("FAIL")).toHaveClass("text-bad");
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("$300,000")).toBeInTheDocument();
    expect(screen.getByText("$215,000")).toBeInTheDocument();
    expect(screen.getByText("+$85,000")).toHaveClass("text-ok");
    expect(screen.getByTestId("issues-bad")).toHaveTextContent("Fleet assigns grounded aircraft VT-ABC");
    expect(screen.getByTestId("issues-warn")).toHaveTextContent("Cargo opposes the change");
    expect(screen.getByRole("meter", { name: "Profit" })).toHaveAttribute("aria-valuenow", "70");
    expect(screen.getByText("21.0 pts")).toBeInTheDocument();
    expect(screen.getByText("Risks (1)")).toBeInTheDocument();
    expect(screen.getByText("Constraints checked (2)")).toBeInTheDocument();
    // Gauge picks up the thresholds saved on the Weights page.
    await waitFor(() => expect(screen.getByText(/review 30 · recommend 80/)).toBeInTheDocument());
  });

  it("colours a negative profit red and a PASS green", () => {
    server.use(...defaultHandlers());
    renderWithProviders(
      <DecisionPanel
        decision={makeDecision({ expected_profit_impact: -5000, validation_result: { constraints: "PASS", verdict: "REVIEW" } })}
        runStatus="COMPLETED"
      />,
    );
    expect(screen.getByText("-$5,000")).toHaveClass("text-bad");
    expect(screen.getByText("PASS")).toHaveClass("text-ok");
  });

  it("renders an older decision without score, verdict, warnings or breakdown gracefully", () => {
    server.use(...defaultHandlers());
    renderWithProviders(
      <DecisionPanel
        decision={makeDecision({ validation_result: { risk: "MEDIUM", constraints: "PASS", conflicts: [] }, risks: [] })}
        runStatus="COMPLETED"
      />,
    );
    expect(screen.getByRole("img", { name: "Decision score: no score" })).toBeInTheDocument();
    expect(screen.getByText(/made before weighted scoring, so it has no verdict/)).toBeInTheDocument();
    expect(screen.getByTestId("breakdown-missing")).toBeInTheDocument();
    expect(screen.queryByTestId("issues-warn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("issues-bad")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Risks \(/)).not.toBeInTheDocument();
    expect(screen.getByText("MEDIUM")).toBeInTheDocument();
  });

  it("copes with an empty validation_result and a null constraints field", () => {
    server.use(...defaultHandlers());
    renderWithProviders(<DecisionPanel decision={makeDecision({ validation_result: {} })} runStatus="COMPLETED" />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("wraps a very long summary instead of overflowing", () => {
    server.use(...defaultHandlers());
    const summary = "Increase ".repeat(200);
    renderWithProviders(<DecisionPanel decision={makeDecision({ summary })} runStatus="COMPLETED" />);
    expect(screen.getByTestId("decision-summary-text")).toHaveClass("break-words");
    expect(screen.getByTestId("decision-summary-text").textContent).toBe(summary);
  });

  it.each([
    ["RUNNING", /still working/],
    ["FAILED", /failed before a decision/],
    ["COMPLETED", /No decision was recorded/],
  ] as const)("explains a missing decision for a %s run", (status, text) => {
    server.use(...defaultHandlers());
    renderWithProviders(<DecisionPanel decision={null} runStatus={status} />);
    expect(screen.getByTestId("decision-empty")).toHaveTextContent(text);
  });

  it("still renders when the weights cannot be loaded", async () => {
    server.use(http.get(api("/api/decision-weights"), () => HttpResponse.json({ detail: "x" }, { status: 500 })));
    renderWithProviders(<DecisionPanel decision={makeDecision()} runStatus="COMPLETED" />);
    await waitFor(() => expect(screen.getByText(/review 45 · recommend 70/)).toBeInTheDocument());
  });
});
