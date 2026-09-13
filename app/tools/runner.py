import time
import uuid
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.bus import EventBus
from app.events.service import emit_event
from app.models.observability import ToolExecution


async def run_tool(
    db: AsyncSession,
    *,
    bus: EventBus,
    run_id: uuid.UUID,
    agent_execution_id: uuid.UUID,
    tool_name: str,
    tool_fn: Callable[..., Awaitable[dict]],
    arguments: dict | None = None,
) -> dict:
    """Execute `tool_fn`, persisting a ToolExecution row and emitting lifecycle events.

    Emits `tool.called` before invocation, then either `tool.completed` (with the
    result recorded) or `tool.failed` (with the error recorded) after. On failure,
    the ToolExecution row carrying the error is flushed BEFORE the exception is
    re-raised, so observability data is never lost even though the caller sees
    the exception propagate.

    Catches bare `Exception` deliberately: `tool_fn` is arbitrary caller-supplied
    code (future tools may fail for any reason — bad SQL, bad data, programmer
    error) and the job here is purely to record + re-raise, not to reclassify
    the error the way provider-specific error narrowing does elsewhere.
    """
    arguments = arguments or {}
    await emit_event(
        db, bus=bus, event_type="tool.called", run_id=run_id,
        agent_execution_id=agent_execution_id,
        payload={"tool_name": tool_name, "arguments": arguments},
    )

    started = time.monotonic()
    try:
        async with db.begin_nested():
            result = await tool_fn(db, **arguments)
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        execution = ToolExecution(
            agent_execution_id=agent_execution_id, tool_name=tool_name, arguments=arguments,
            result=None, data_source="postgres", duration_ms=duration_ms, error=str(exc),
        )
        db.add(execution)
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="tool.failed", run_id=run_id,
            agent_execution_id=agent_execution_id,
            payload={"tool_name": tool_name, "error": str(exc)}, severity="ERROR",
        )
        raise

    duration_ms = int((time.monotonic() - started) * 1000)
    execution = ToolExecution(
        agent_execution_id=agent_execution_id, tool_name=tool_name, arguments=arguments,
        result=result, data_source="postgres", duration_ms=duration_ms,
    )
    db.add(execution)
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="tool.completed", run_id=run_id,
        agent_execution_id=agent_execution_id,
        payload={"tool_name": tool_name, "duration_ms": duration_ms},
    )
    return result
