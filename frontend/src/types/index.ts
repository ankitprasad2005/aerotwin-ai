export type AgentExecutionStatus =
  | "WAITING"
  | "QUEUED"
  | "RUNNING"
  | "WAITING_FOR_LLM"
  | "WAITING_FOR_TOOL"
  | "COMPLETED"
  | "FAILED"
  | "RETRYING"
  | "BLOCKED";

export type OrchestrationRunStatus = "RUNNING" | "COMPLETED" | "FAILED";

export type EventSeverity = "INFO" | "WARN" | "ERROR";

export interface OrchestrationRun {
  id: string;
  objective: string;
  status: OrchestrationRunStatus;
  created_at: string;
  completed_at: string | null;
}

export interface AgentExecution {
  id: string;
  run_id: string;
  agent_type: string;
  status: AgentExecutionStatus;
  task: string;
  elapsed_ms: number | null;
  total_tokens: number | null;
  created_at: string;
}

export interface ContextSnapshot {
  id: string;
  agent_execution_id: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface LLMExecution {
  id: string;
  agent_execution_id: string;
  provider: string;
  model: string;
  request_id: string;
  system_instructions: string;
  context: Record<string, unknown>;
  task: string;
  available_tools: string[];
  model_parameters: Record<string, unknown>;
  raw_response: Record<string, unknown>;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number | null;
  duration_ms: number;
  retry_count: number;
  // Only ever "COMPLETED" today — a failed LLM call never creates an LLMExecution row
  // (see app/agents/runner.py). Widen if a future backend change adds a status.
  status: "COMPLETED";
  created_at: string;
}

export interface ToolExecution {
  id: string;
  agent_execution_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  data_source: string;
  duration_ms: number;
  error: string | null;
  created_at: string;
}

export interface Decision {
  id: string;
  run_id: string;
  summary: string;
  expected_profit_impact: number;
  expected_revenue_impact: number;
  expected_cost_impact: number;
  confidence: number;
  risks: string[];
  constraints_checked: string[];
  validation_result: Record<string, unknown>;
  // No other value exists in Phase 1 — decisions are recommendation-only (see design doc §3).
  status: "RECOMMENDED";
  agents_involved: string[];
  created_at: string;
}

export interface AgentExecutionDetail extends AgentExecution {
  context_snapshot: ContextSnapshot | null;
  llm_execution: LLMExecution | null;
  tool_executions: ToolExecution[];
}

export interface RunDetail extends OrchestrationRun {
  agent_executions: AgentExecution[];
  decision: Decision | null;
}

export interface EventRecord {
  id: string;
  run_id: string | null;
  agent_execution_id: string | null;
  event_type: string;
  severity: EventSeverity;
  entity_type: string | null;
  entity_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface GraphNodeData {
  id: string;
  type: string;
  status: string;
  // Omitted from the wire payload entirely for nodes without one (not serialized as
  // null) — this endpoint has no Pydantic response_model, see app/api/runs.py.
  agent_execution_id?: string;
  decision_id?: string;
}

export interface GraphEdgeData {
  source: string;
  target: string;
}

export interface RunGraph {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
}
