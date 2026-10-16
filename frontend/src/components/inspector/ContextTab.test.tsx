import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContextTab } from "./ContextTab";

describe("ContextTab", () => {
  it("shows a placeholder when there is no context snapshot", () => {
    render(<ContextTab contextSnapshot={null} />);
    expect(screen.getByText("[NO CONTEXT SNAPSHOT]")).toBeInTheDocument();
  });

  it("renders one collapsible section per top-level payload key", () => {
    render(
      <ContextTab
        contextSnapshot={{
          id: "1",
          agent_execution_id: "2",
          payload: { objective: "Improve profitability", entities: { routes: [] } },
          created_at: "2026-09-11T00:00:00Z",
        }}
      />,
    );
    expect(screen.getByText("objective")).toBeInTheDocument();
    expect(screen.getByText("entities")).toBeInTheDocument();
  });

  it("renders the JSON-stringified value inside each section", () => {
    render(
      <ContextTab
        contextSnapshot={{
          id: "1",
          agent_execution_id: "2",
          payload: { objective: "Improve profitability" },
          created_at: "2026-09-11T00:00:00Z",
        }}
      />,
    );
    expect(screen.getByText(/"Improve profitability"/)).toBeInTheDocument();
  });

  it("explains routed evidence only when evidence_routing is non-empty", () => {
    const base = { id: "c", agent_execution_id: "a", payload: { objective: "x" }, created_at: "2026-10-16T00:00:00Z" };
    const { rerender } = render(<ContextTab contextSnapshot={base} />);
    expect(screen.queryByTestId("evidence-routing")).toBeNull();
    rerender(
      <ContextTab
        contextSnapshot={{
          ...base,
          evidence_routing: [
            { provider: "eia_brent", topic: "fuel" },
            { provider: "eia_jet_fuel", topic: "fuel" },
            { provider: "aviation_weather_taf", topic: "weather" },
          ],
        }}
      />,
    );
    expect(screen.getByTestId("evidence-routing")).toHaveTextContent("Added because the objective mentions: fuel, weather");
  });
});
