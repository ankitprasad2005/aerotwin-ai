import pytest
from sqlalchemy import select

from app.events.bus import EventBus
from app.models.observability import (
    AgentExecution, AgentExecutionStatus, OrchestrationRun, OrchestrationRunStatus, ToolExecution,
)
from app.tools.runner import run_tool


async def _make_run_and_execution(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()
    execution = AgentExecution(
        run_id=run.id, agent_type="NETWORK", status=AgentExecutionStatus.RUNNING.value, task="t"
    )
    db_session.add(execution)
    await db_session.flush()
    return run, execution


async def test_run_tool_persists_execution_and_emits_events(db_session):
    run, execution = await _make_run_and_execution(db_session)
    bus = EventBus()
    queue = bus.subscribe()

    async def fake_tool(db, **kwargs):
        return {"ok": True}

    result = await run_tool(
        db_session, bus=bus, run_id=run.id, agent_execution_id=execution.id,
        tool_name="fake_tool", tool_fn=fake_tool,
    )

    assert result == {"ok": True}
    stored = (
        await db_session.execute(
            select(ToolExecution).where(ToolExecution.agent_execution_id == execution.id)
        )
    ).scalar_one()
    assert stored.tool_name == "fake_tool"
    assert stored.error is None

    called_event = await queue.get()
    completed_event = await queue.get()
    assert called_event["event_type"] == "tool.called"
    assert completed_event["event_type"] == "tool.completed"


async def test_run_tool_records_error_and_reraises_on_failure(db_session):
    run, execution = await _make_run_and_execution(db_session)
    bus = EventBus()
    queue = bus.subscribe()

    async def failing_tool(db, **kwargs):
        raise ValueError("data source unreachable")

    with pytest.raises(ValueError):
        await run_tool(
            db_session, bus=bus, run_id=run.id, agent_execution_id=execution.id,
            tool_name="failing_tool", tool_fn=failing_tool,
        )

    stored = (
        await db_session.execute(
            select(ToolExecution).where(ToolExecution.agent_execution_id == execution.id)
        )
    ).scalar_one()
    assert stored.error == "data source unreachable"

    called_event = await queue.get()
    failed_event = await queue.get()
    assert called_event["event_type"] == "tool.called"
    assert failed_event["event_type"] == "tool.failed"
    assert failed_event["severity"] == "ERROR"
