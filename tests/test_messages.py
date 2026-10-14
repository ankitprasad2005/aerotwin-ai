from sqlalchemy import select

from app.events.bus import EventBus
from app.models.observability import (
    AgentExecution, AgentMessage, ContextSnapshot, Event, OrchestrationRun, OrchestrationRunStatus,
)
from app.orchestrator.messages import send_message


async def _run(db_session):
    run = OrchestrationRun(objective="x", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()
    return run


async def test_send_message_persists_the_message_and_emits_an_event(db_session):
    run = await _run(db_session)
    bus = EventBus()
    queue = bus.subscribe()

    message = await send_message(
        db_session, bus=bus, run_id=run.id, sender="NETWORK_AGENT", receiver="ORCHESTRATOR",
        message_type="RECOMMENDATION", payload={"route": "BOM-DEL"},
    )

    stored = (await db_session.execute(select(AgentMessage))).scalar_one()
    assert stored.id == message.id
    assert (stored.sender, stored.receiver, stored.message_type) == (
        "NETWORK_AGENT", "ORCHESTRATOR", "RECOMMENDATION"
    )
    assert stored.payload == {"route": "BOM-DEL"}
    assert stored.context_id is None

    event = (await db_session.execute(select(Event).where(Event.event_type == "agent.message_sent"))).scalar_one()
    assert event.run_id == run.id
    assert event.payload == {
        "message_id": str(message.id), "sender": "NETWORK_AGENT", "receiver": "ORCHESTRATOR",
        "message_type": "RECOMMENDATION",
    }
    assert queue.get_nowait()["event_type"] == "agent.message_sent"


async def test_send_message_links_the_context_snapshot(db_session):
    run = await _run(db_session)
    execution = AgentExecution(run_id=run.id, agent_type="NETWORK", task="t", status="COMPLETED")
    db_session.add(execution)
    await db_session.flush()
    snapshot = ContextSnapshot(agent_execution_id=execution.id, payload={})
    db_session.add(snapshot)
    await db_session.flush()

    message = await send_message(
        db_session, bus=EventBus(), run_id=run.id, sender="A", receiver="B",
        message_type="RECOMMENDATION", payload={}, context_id=snapshot.id,
    )

    assert message.context_id == snapshot.id
