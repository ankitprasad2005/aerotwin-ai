import asyncio

from sqlalchemy import select

from app.events.bus import EventBus
from app.events.service import emit_event
from app.models.observability import Event, OrchestrationRun, OrchestrationRunStatus


async def test_emit_event_persists_row(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()

    event = await emit_event(
        db_session,
        bus=EventBus(),
        event_type="orchestration.started",
        run_id=run.id,
        agent_execution_id=None,
        payload={"objective": "x"},
    )

    fetched = (await db_session.execute(select(Event).where(Event.id == event.id))).scalar_one()
    assert fetched.event_type == "orchestration.started"
    assert fetched.severity == "INFO"


async def test_emit_event_broadcasts_to_bus(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()

    bus = EventBus()
    queue = bus.subscribe()

    await emit_event(
        db_session, bus=bus, event_type="agent.started", run_id=run.id,
        agent_execution_id=None, payload={"agent_type": "NETWORK"},
    )

    message = await asyncio.wait_for(queue.get(), timeout=1)
    assert message["event_type"] == "agent.started"
    assert message["payload"] == {"agent_type": "NETWORK"}


async def test_emit_event_accepts_severity_and_entity_fields(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()

    event = await emit_event(
        db_session, bus=EventBus(), event_type="tool.failed", run_id=run.id,
        agent_execution_id=None, payload={"error": "timeout"}, severity="ERROR",
        entity_type="Route", entity_id="BOM-DEL",
    )

    assert event.severity == "ERROR"
    assert event.entity_type == "Route"
    assert event.entity_id == "BOM-DEL"


async def test_emit_event_does_not_commit(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()

    await emit_event(
        db_session, bus=EventBus(), event_type="orchestration.started", run_id=run.id,
        agent_execution_id=None, payload={},
    )
    await db_session.rollback()

    result = await db_session.execute(select(Event).where(Event.run_id == run.id))
    assert result.scalars().first() is None
