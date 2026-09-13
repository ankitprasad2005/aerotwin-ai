import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentExecutionDetail } from "../../types";
import { OverviewTab } from "./OverviewTab";

function makeDetail(overrides: Partial<AgentExecutionDetail> = {}): AgentExecutionDetail {
  return {
    id: "1",
    run_id: "2",
    agent_type: "NETWORK",
    status: "COMPLETED",
    task: "Identify profitable route frequency changes.",
    elapsed_ms: 4200,
    total_tokens: 180,
    created_at: "2026-09-11T00:00:00Z",
    context_snapshot: null,
    llm_execution: null,
    tool_executions: [],
    ...overrides,
  };
}

describe("OverviewTab", () => {
  it("renders status, agent type, task, elapsed time, and tokens", () => {
    render(<OverviewTab detail={makeDetail()} />);
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("NETWORK")).toBeInTheDocument();
    expect(screen.getByText("Identify profitable route frequency changes.")).toBeInTheDocument();
    expect(screen.getByText("4.2s")).toBeInTheDocument();
    expect(screen.getByText("180")).toBeInTheDocument();
  });

  it("renders a dash when elapsed_ms and total_tokens are null", () => {
    render(<OverviewTab detail={makeDetail({ elapsed_ms: null, total_tokens: null })} />);
    expect(screen.getAllByText("—")).toHaveLength(2);
  });
});
