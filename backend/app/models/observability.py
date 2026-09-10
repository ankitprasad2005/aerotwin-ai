import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class OrchestrationRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentExecutionStatus(str, enum.Enum):
    WAITING = "WAITING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_LLM = "WAITING_FOR_LLM"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    BLOCKED = "BLOCKED"


class EventSeverity(str, enum.Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class OrchestrationRun(TimestampedBase):
    __tablename__ = "orchestration_runs"

    objective: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=OrchestrationRunStatus.RUNNING.value)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentExecution(TimestampedBase):
    __tablename__ = "agent_executions"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orchestration_runs.id"), nullable=False, index=True
    )
    agent_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=AgentExecutionStatus.WAITING.value)
    task: Mapped[str] = mapped_column(String, nullable=False)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ContextSnapshot(TimestampedBase):
    __tablename__ = "context_snapshots"

    agent_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_executions.id"), nullable=False, index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class LLMExecution(TimestampedBase):
    __tablename__ = "llm_executions"

    agent_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_executions.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    request_id: Mapped[str] = mapped_column(String, nullable=False)
    system_instructions: Mapped[str] = mapped_column(String, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    task: Mapped[str] = mapped_column(String, nullable=False)
    available_tools: Mapped[list] = mapped_column(JSONB, nullable=False)
    model_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False)


class ToolExecution(TimestampedBase):
    __tablename__ = "tool_executions"

    agent_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_executions.id"), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    data_source: Mapped[str] = mapped_column(String, nullable=False, default="postgres")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class AgentMessage(TimestampedBase):
    __tablename__ = "agent_messages"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orchestration_runs.id"), nullable=False, index=True
    )
    context_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("context_snapshots.id"), nullable=True, index=True
    )
    sender: Mapped[str] = mapped_column(String, nullable=False)
    receiver: Mapped[str] = mapped_column(String, nullable=False)
    message_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Decision(TimestampedBase):
    __tablename__ = "decisions"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orchestration_runs.id"), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(String, nullable=False)
    expected_profit_impact: Mapped[float] = mapped_column(Float, nullable=False)
    expected_revenue_impact: Mapped[float] = mapped_column(Float, nullable=False)
    expected_cost_impact: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    constraints_checked: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    validation_result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="RECOMMENDED")
    agents_involved: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class Event(TimestampedBase):
    """Append-only pipeline log; every other write in the system emits one row here.

    entity_type/entity_id are a polymorphic reference into the Digital Twin
    (e.g. entity_type="aircraft", entity_id=<Aircraft.id as str>) used to filter
    the event stream by the twin entity an event relates to. No FK/enum
    constraint is enforced here since entity_type spans multiple tables.
    """

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_run_id_created_at", "run_id", "created_at"),)

    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orchestration_runs.id"), nullable=True, index=True
    )
    agent_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_executions.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, default=EventSeverity.INFO.value, index=True)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
