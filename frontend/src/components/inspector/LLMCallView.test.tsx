import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useDebugStore } from "../../stores/debugStore";
import type { LLMExecution } from "../../types";
import { LLMCallView } from "./LLMCallView";

function makeLLMExecution(overrides: Partial<LLMExecution> = {}): LLMExecution {
  return {
    id: "4",
    agent_execution_id: "1",
    provider: "openai",
    model: "gpt-4o-mini",
    request_id: "req-1",
    system_instructions: "You are the network agent.",
    context: { a: 1 },
    task: "t",
    available_tools: ["query_route_profitability"],
    model_parameters: {},
    raw_response: { id: "req-1" },
    input_tokens: 100,
    output_tokens: 50,
    total_tokens: 150,
    estimated_cost: 0.001,
    duration_ms: 4200,
    retry_count: 0,
    status: "COMPLETED",
    created_at: "2026-09-11T00:00:00Z",
    ...overrides,
  };
}

describe("LLMCallView", () => {
  it("shows a placeholder when there is no LLM execution yet", () => {
    render(<LLMCallView llmExecution={null} />);
    expect(screen.getByText("[NO LLM CALL YET]")).toBeInTheDocument();
  });

  it("renders provider, model, duration, and token counts", () => {
    render(<LLMCallView llmExecution={makeLLMExecution()} />);
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o-mini")).toBeInTheDocument();
    expect(screen.getByText("4.2s")).toBeInTheDocument();
    expect(screen.getByText("100 in / 50 out / 150 total")).toBeInTheDocument();
  });

  it("renders the system instructions inside a collapsible section", () => {
    render(<LLMCallView llmExecution={makeLLMExecution()} />);
    expect(screen.getByText("You are the network agent.")).toBeInTheDocument();
  });

  it("shows a raw response section only when debug mode is enabled", () => {
    useDebugStore.setState({ enabled: false });
    const { rerender } = render(<LLMCallView llmExecution={makeLLMExecution()} />);
    expect(screen.queryByText("Raw response (debug)")).not.toBeInTheDocument();

    useDebugStore.setState({ enabled: true });
    rerender(<LLMCallView llmExecution={makeLLMExecution()} />);
    expect(screen.getByText("Raw response (debug)")).toBeInTheDocument();
    useDebugStore.setState({ enabled: false });
  });
});
