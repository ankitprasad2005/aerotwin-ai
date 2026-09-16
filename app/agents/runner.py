import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.spec import AgentSpec
from app.events.bus import EventBus
from app.events.service import emit_event
from app.llm.base import LLMProvider
from app.models.observability import AgentExecution, AgentExecutionStatus, ContextSnapshot, LLMExecution
from app.tools.runner import run_tool


class AgentRunError(Exception):
    """Raised when any stage of run_agent fails.

    Carries `agent_execution_id` (and `agent_type`) so a caller orchestrating
    multiple agents (Task 15) can identify which agent failed without having
    to catch and inspect the underlying cause separately.
    """

    def __init__(self, message: str, agent_execution_id: uuid.UUID, agent_type: str):
        super().__init__(message)
        self.agent_execution_id = agent_execution_id
        self.agent_type = agent_type


async def run_agent(
    db: AsyncSession,
    *,
    bus: EventBus,
    run_id: uuid.UUID,
    spec: AgentSpec,
    context_payload: dict,
    llm_provider: LLMProvider,
    iteration_id: uuid.UUID | None = None,
):
    """Run one agent through context -> tool -> LLM -> validate, persisting observability rows.

    Every AgentExecutionStatus transition is flushed to the session before the
    subsequent emit_event call, so any event emitted always reflects state that
    is at least flushed (visible within the transaction) at the time it fires.
    """
    execution = AgentExecution(
        run_id=run_id, iteration_id=iteration_id, agent_type=spec.agent_type,
        task=spec.task_description, status=AgentExecutionStatus.QUEUED.value,
    )
    db.add(execution)
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="agent.started", run_id=run_id, agent_execution_id=execution.id,
        payload={"agent_type": spec.agent_type, "task": spec.task_description},
    )

    started = time.monotonic()
    execution.status = AgentExecutionStatus.RUNNING.value
    await db.flush()

    snapshot = ContextSnapshot(agent_execution_id=execution.id, payload=context_payload)
    db.add(snapshot)
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="context.created", run_id=run_id, agent_execution_id=execution.id,
        payload={"context_snapshot_id": str(snapshot.id)},
    )

    execution.status = AgentExecutionStatus.WAITING_FOR_TOOL.value
    await db.flush()
    try:
        tool_result = await run_tool(
            db, bus=bus, run_id=run_id, agent_execution_id=execution.id,
            tool_name=spec.tool_name, tool_fn=spec.tool_fn,
        )
    except Exception as exc:
        execution.status = AgentExecutionStatus.FAILED.value
        execution.elapsed_ms = int((time.monotonic() - started) * 1000)
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="agent.failed", run_id=run_id, agent_execution_id=execution.id,
            payload={"error": str(exc)}, severity="ERROR",
        )
        raise AgentRunError(f"tool call failed: {exc}", execution.id, spec.agent_type) from exc

    execution.status = AgentExecutionStatus.WAITING_FOR_LLM.value
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="llm.request", run_id=run_id, agent_execution_id=execution.id,
        payload={"tool_result_included": True},
    )

    llm_context = {**context_payload, "tool_result": tool_result}
    try:
        llm_response = await llm_provider.complete(
            system_instructions=spec.system_instructions,
            context=llm_context,
            task=spec.task_description,
            available_tools=[spec.tool_name],
            output_schema=spec.output_schema,
        )

        llm_execution = LLMExecution(
            agent_execution_id=execution.id,
            provider=llm_response.provider,
            model=llm_response.model,
            request_id=llm_response.request_id,
            system_instructions=spec.system_instructions,
            context=llm_context,
            task=spec.task_description,
            available_tools=[spec.tool_name],
            model_parameters={},
            raw_response=llm_response.raw_response,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
            total_tokens=llm_response.total_tokens,
            estimated_cost=llm_response.estimated_cost,
            duration_ms=llm_response.duration_ms,
            retry_count=llm_response.retry_count,
            status="COMPLETED",
        )
        db.add(llm_execution)
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="llm.response", run_id=run_id, agent_execution_id=execution.id,
            payload={"llm_execution_id": str(llm_execution.id), "total_tokens": llm_response.total_tokens},
        )

        execution.status = AgentExecutionStatus.COMPLETED.value
        execution.total_tokens = llm_response.total_tokens
        execution.elapsed_ms = int((time.monotonic() - started) * 1000)
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="agent.completed", run_id=run_id, agent_execution_id=execution.id,
            payload={"recommendation": llm_response.parsed.model_dump()},
        )
    except Exception as exc:
        execution.status = AgentExecutionStatus.FAILED.value
        execution.elapsed_ms = int((time.monotonic() - started) * 1000)
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="llm.failed", run_id=run_id, agent_execution_id=execution.id,
            payload={"error": str(exc)}, severity="ERROR",
        )
        await emit_event(
            db, bus=bus, event_type="agent.failed", run_id=run_id, agent_execution_id=execution.id,
            payload={"error": str(exc)}, severity="ERROR",
        )
        raise AgentRunError(f"LLM call failed: {exc}", execution.id, spec.agent_type) from exc

    return execution, llm_response.parsed
