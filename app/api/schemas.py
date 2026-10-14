import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrchestrationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    objective: str
    status: str
    created_at: datetime
    completed_at: datetime | None


class AgentExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID
    agent_type: str
    status: str
    task: str
    elapsed_ms: int | None
    total_tokens: int | None
    created_at: datetime
    # The agent's structured output (route/action/impacts/risks/reasoning), attached by the API
    # from the agent.completed event; None until the agent completes.
    recommendation: dict | None = None


class ContextSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    agent_execution_id: uuid.UUID
    payload: dict
    created_at: datetime


class LLMExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    agent_execution_id: uuid.UUID
    provider: str
    model: str
    request_id: str
    system_instructions: str
    context: dict
    task: str
    available_tools: list
    model_parameters: dict
    raw_response: dict
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float | None
    duration_ms: int
    retry_count: int
    status: str
    created_at: datetime


class ToolExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    agent_execution_id: uuid.UUID
    tool_name: str
    arguments: dict
    result: dict | None
    data_source: str
    duration_ms: int
    error: str | None
    created_at: datetime


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID
    summary: str
    expected_profit_impact: float
    expected_revenue_impact: float
    expected_cost_impact: float
    confidence: float
    risks: list
    constraints_checked: list
    validation_result: dict
    status: str
    agents_involved: list
    created_at: datetime


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID
    context_id: uuid.UUID | None
    sender: str
    receiver: str
    message_type: str
    payload: dict
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID | None
    agent_execution_id: uuid.UUID | None
    event_type: str
    severity: str
    entity_type: str | None
    entity_id: str | None
    payload: dict
    created_at: datetime


class AgentExecutionDetailOut(AgentExecutionOut):
    context_snapshot: ContextSnapshotOut | None
    llm_execution: LLMExecutionOut | None
    tool_executions: list[ToolExecutionOut]


class RunIterationOut(BaseModel):
    """One prompt's pass through the pipeline, with the work it produced."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID
    sequence: int
    objective: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    agent_executions: list[AgentExecutionOut] = []
    decision: DecisionOut | None = None


class RunDetailOut(OrchestrationRunOut):
    # Flat lists cover the whole run; `iterations` groups the same work per prompt. `decision` is
    # the most recent one, so a single-prompt run reads exactly as it did before follow-ups existed.
    agent_executions: list[AgentExecutionOut]
    decision: DecisionOut | None
    iterations: list[RunIterationOut] = []


class RunCreate(BaseModel):
    # Strip before the length check, so a whitespace-only objective is rejected instead of
    # launching a full orchestration run (two LLM calls) with nothing to optimize for.
    model_config = ConfigDict(str_strip_whitespace=True)
    objective: str = Field(min_length=1, max_length=2000)
