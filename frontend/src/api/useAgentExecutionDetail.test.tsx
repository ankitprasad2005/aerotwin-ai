import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { createQueryWrapper } from "../test/renderWithQueryClient";
import {
  useAgentExecutionDetail,
  useDecisionDetail,
  useLLMExecutionDetail,
  useToolExecutionDetail,
} from "./useAgentExecutionDetail";

describe("useAgentExecutionDetail", () => {
  it("does not fetch when id is undefined", () => {
    const { result } = renderHook(() => useAgentExecutionDetail(undefined), {
      wrapper: createQueryWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches agent execution detail including nested context/llm/tool data", async () => {
    server.use(
      http.get("http://localhost:8000/api/agent-executions/1", () =>
        HttpResponse.json({
          id: "1",
          run_id: "2",
          agent_type: "NETWORK",
          status: "COMPLETED",
          task: "t",
          elapsed_ms: 4200,
          recommendation: null,
          total_tokens: 180,
          created_at: "2026-09-11T00:00:00Z",
          context_snapshot: { id: "3", agent_execution_id: "1", payload: { objective: "x" }, created_at: "2026-09-11T00:00:00Z" },
          llm_execution: null,
          tool_executions: [],
        }),
      ),
    );
    const { result } = renderHook(() => useAgentExecutionDetail("1"), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.context_snapshot?.payload).toEqual({ objective: "x" });
  });
});

describe("useLLMExecutionDetail", () => {
  it("fetches LLM execution detail", async () => {
    server.use(
      http.get("http://localhost:8000/api/llm-executions/4", () =>
        HttpResponse.json({
          id: "4",
          agent_execution_id: "1",
          provider: "openai",
          model: "gpt-4o-mini",
          request_id: "req-1",
          system_instructions: "sys",
          context: {},
          task: "t",
          available_tools: [],
          model_parameters: {},
          raw_response: {},
          input_tokens: 100,
          output_tokens: 50,
          total_tokens: 150,
          estimated_cost: 0.001,
          duration_ms: 4200,
          retry_count: 0,
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
        }),
      ),
    );
    const { result } = renderHook(() => useLLMExecutionDetail("4"), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.model).toBe("gpt-4o-mini");
  });
});

describe("useToolExecutionDetail", () => {
  it("fetches tool execution detail", async () => {
    server.use(
      http.get("http://localhost:8000/api/tool-executions/5", () =>
        HttpResponse.json({
          id: "5",
          agent_execution_id: "1",
          tool_name: "query_route_profitability",
          arguments: {},
          result: { routes: [] },
          data_source: "postgres",
          duration_ms: 80,
          error: null,
          created_at: "2026-09-11T00:00:00Z",
        }),
      ),
    );
    const { result } = renderHook(() => useToolExecutionDetail("5"), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.tool_name).toBe("query_route_profitability");
  });
});

describe("useDecisionDetail", () => {
  it("fetches decision detail", async () => {
    server.use(
      http.get("http://localhost:8000/api/decisions/6", () =>
        HttpResponse.json({
          id: "6",
          run_id: "2",
          summary: "Increase BOM-DEL frequency",
          expected_profit_impact: 85000,
          expected_revenue_impact: 300000,
          expected_cost_impact: 215000,
          confidence: 0.82,
          risks: [],
          constraints_checked: [],
          validation_result: {},
          status: "RECOMMENDED",
          agents_involved: [],
          created_at: "2026-09-11T00:00:00Z",
        }),
      ),
    );
    const { result } = renderHook(() => useDecisionDetail("6"), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.summary).toBe("Increase BOM-DEL frequency");
  });
});
