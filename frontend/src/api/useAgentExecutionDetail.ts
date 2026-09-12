import { useQuery } from "@tanstack/react-query";
import type { AgentExecutionDetail, Decision, LLMExecution, ToolExecution } from "../types";
import { apiFetch } from "./client";

export function useAgentExecutionDetail(id: string | undefined) {
  return useQuery({
    queryKey: ["agent-executions", id],
    queryFn: () => apiFetch<AgentExecutionDetail>(`/api/agent-executions/${id}`),
    enabled: Boolean(id),
  });
}

export function useLLMExecutionDetail(id: string | undefined) {
  return useQuery({
    queryKey: ["llm-executions", id],
    queryFn: () => apiFetch<LLMExecution>(`/api/llm-executions/${id}`),
    enabled: Boolean(id),
  });
}

export function useToolExecutionDetail(id: string | undefined) {
  return useQuery({
    queryKey: ["tool-executions", id],
    queryFn: () => apiFetch<ToolExecution>(`/api/tool-executions/${id}`),
    enabled: Boolean(id),
  });
}

export function useDecisionDetail(id: string | undefined) {
  return useQuery({
    queryKey: ["decisions", id],
    queryFn: () => apiFetch<Decision>(`/api/decisions/${id}`),
    enabled: Boolean(id),
  });
}
