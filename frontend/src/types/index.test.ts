import { describe, expect, it } from "vitest";
import type {
  AgentExecution,
  AgentExecutionDetail,
  ContextSnapshot,
  Decision,
  EventRecord,
  LLMExecution,
  OrchestrationRun,
  RunDetail,
  RunGraph,
  ToolExecution,
} from "./index";

describe("API types", () => {
  it("OrchestrationRun accepts a real backend-shaped sample", () => {
    const run: OrchestrationRun = {
      id: "8f14e45f-ceea-467e-adde-3f4694a483c0",
      objective: "Improve airline profitability",
      status: "COMPLETED",
      created_at: "2026-09-11T00:00:00Z",
      completed_at: "2026-09-11T00:00:05Z",
    };
    expect(run.status).toBe("COMPLETED");
  });

  it("AgentExecution and AgentExecutionDetail accept real backend-shaped samples", () => {
    const execution: AgentExecution = {
      id: "1",
      run_id: "2",
      agent_type: "NETWORK",
      status: "COMPLETED",
      task: "Identify profitable route frequency changes.",
      elapsed_ms: 4200,
      recommendation: null,
      total_tokens: 180,
      created_at: "2026-09-11T00:00:00Z",
    };
    const contextSnapshot: ContextSnapshot = {
      id: "3",
      agent_execution_id: execution.id,
      payload: { objective: "x" },
      created_at: "2026-09-11T00:00:00Z",
    };
    const llmExecution: LLMExecution = {
      id: "4",
      agent_execution_id: execution.id,
      provider: "openai",
      model: "gpt-4o-mini",
      request_id: "req-1",
      system_instructions: "sys",
      context: { a: 1 },
      task: execution.task,
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
    };
    const toolExecution: ToolExecution = {
      id: "5",
      agent_execution_id: execution.id,
      tool_name: "query_route_profitability",
      arguments: {},
      result: { routes: [] },
      data_source: "postgres",
      duration_ms: 80,
      error: null,
      created_at: "2026-09-11T00:00:00Z",
    };
    const detail: AgentExecutionDetail = {
      ...execution,
      context_snapshot: contextSnapshot,
      llm_execution: llmExecution,
      tool_executions: [toolExecution],
    };
    expect(detail.tool_executions).toHaveLength(1);
  });

  it("Decision accepts a real backend-shaped sample", () => {
    const decision: Decision = {
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
    expect(decision.status).toBe("RECOMMENDED");
  });

  it("RunDetail composes OrchestrationRun with agent_executions and decision", () => {
    const detail: RunDetail = {
      id: "2",
      objective: "x",
      status: "COMPLETED",
      created_at: "2026-09-11T00:00:00Z",
      completed_at: null,
      agent_executions: [],
      decision: null,
      iterations: [
        {
          id: "i1",
          run_id: "2",
          sequence: 1,
          objective: "x",
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: null,
          agent_executions: [],
          decision: null,
        },
      ],
    };
    expect(detail.decision).toBeNull();
    expect(detail.iterations[0].sequence).toBe(1);
  });

  it("EventRecord accepts a real backend-shaped sample", () => {
    const event: EventRecord = {
      id: "7",
      run_id: "2",
      agent_execution_id: "1",
      event_type: "agent.completed",
      severity: "INFO",
      entity_type: null,
      entity_id: null,
      payload: { summary: "Network agent completed" },
      created_at: "2026-09-11T00:00:00Z",
    };
    expect(event.severity).toBe("INFO");
  });

  it("RunGraph accepts a real backend-shaped sample", () => {
    const graph: RunGraph = {
      nodes: [
        { id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED" },
        { id: "agent-1", type: "NETWORK_AGENT", status: "COMPLETED", agent_execution_id: "1" },
      ],
      edges: [{ source: "orchestrator", target: "agent-1" }],
    };
    expect(graph.nodes).toHaveLength(2);
  });
});
