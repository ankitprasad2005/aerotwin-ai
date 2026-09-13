import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useDebugStore } from "../../stores/debugStore";
import type { ToolExecution } from "../../types";
import { ToolCallView } from "./ToolCallView";

function makeTool(overrides: Partial<ToolExecution> = {}): ToolExecution {
  return {
    id: "5",
    agent_execution_id: "1",
    tool_name: "query_route_profitability",
    arguments: {},
    result: { routes: [] },
    data_source: "postgres",
    duration_ms: 80,
    error: null,
    created_at: "2026-09-11T00:00:00Z",
    ...overrides,
  };
}

describe("ToolCallView", () => {
  it("shows a placeholder when there are no tool calls", () => {
    render(<ToolCallView toolExecutions={[]} />);
    expect(screen.getByText("[NO TOOL CALLS YET]")).toBeInTheDocument();
  });

  it("renders the tool name and duration for a successful call", () => {
    render(<ToolCallView toolExecutions={[makeTool()]} />);
    expect(screen.getByText("query_route_profitability")).toBeInTheDocument();
    expect(screen.getByText(/80ms/)).toBeInTheDocument();
  });

  it("renders an error message for a failed call instead of the result", () => {
    render(<ToolCallView toolExecutions={[makeTool({ error: "data source unreachable", result: null })]} />);
    expect(screen.getByText("[ERROR: data source unreachable]")).toBeInTheDocument();
  });

  it("renders one entry per tool execution", () => {
    render(
      <ToolCallView
        toolExecutions={[makeTool({ id: "5" }), makeTool({ id: "6", tool_name: "query_fleet_status" })]}
      />,
    );
    expect(screen.getByText("query_route_profitability")).toBeInTheDocument();
    expect(screen.getByText("query_fleet_status")).toBeInTheDocument();
  });

  it("shows an arguments section only when debug mode is enabled", () => {
    useDebugStore.setState({ enabled: false });
    const { rerender } = render(
      <ToolCallView toolExecutions={[makeTool({ arguments: { route_code: "BOM-DEL" } })]} />,
    );
    expect(screen.queryByText("Arguments (debug)")).not.toBeInTheDocument();

    useDebugStore.setState({ enabled: true });
    rerender(<ToolCallView toolExecutions={[makeTool({ arguments: { route_code: "BOM-DEL" } })]} />);
    expect(screen.getByText("Arguments (debug)")).toBeInTheDocument();
    useDebugStore.setState({ enabled: false });
  });
});
