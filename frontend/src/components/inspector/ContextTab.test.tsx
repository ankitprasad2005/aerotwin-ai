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
});
