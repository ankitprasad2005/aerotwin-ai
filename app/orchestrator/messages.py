import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.bus import EventBus
from app.events.service import emit_event
from app.models.observability import AgentMessage


async def send_message(
    db: AsyncSession,
    *,
    bus: EventBus,
    run_id: uuid.UUID,
    sender: str,
    receiver: str,
    message_type: str,
    payload: dict,
    context_id: uuid.UUID | None = None,
) -> AgentMessage:
    """Persist an inter-agent message and emit `agent.message_sent` (flushes, never commits)."""
    message = AgentMessage(
        run_id=run_id, context_id=context_id, sender=sender, receiver=receiver,
        message_type=message_type, payload=payload,
    )
    db.add(message)
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="agent.message_sent", run_id=run_id, agent_execution_id=None,
        payload={
            "message_id": str(message.id), "sender": sender, "receiver": receiver,
            "message_type": message_type,
        },
    )
    return message
