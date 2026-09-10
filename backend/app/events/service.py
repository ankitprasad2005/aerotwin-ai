import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.bus import EventBus
from app.models.observability import Event, EventSeverity

logger = logging.getLogger(__name__)


def _serialize(event: Event) -> dict:
    return {
        "id": str(event.id),
        "run_id": str(event.run_id) if event.run_id else None,
        "agent_execution_id": str(event.agent_execution_id) if event.agent_execution_id else None,
        "event_type": event.event_type,
        "severity": event.severity,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }


async def emit_event(
    db: AsyncSession,
    *,
    bus: EventBus,
    event_type: str,
    run_id: uuid.UUID | None,
    agent_execution_id: uuid.UUID | None,
    payload: dict,
    severity: str = EventSeverity.INFO.value,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> Event:
    """Persist an Event row and broadcast it, without committing the caller's transaction.

    Flushes only (never commits) — safe to call mid-transaction from any pipeline
    step. The broadcast fires immediately after flush, i.e. before the caller's
    outer transaction commits: if the outer transaction later rolls back,
    subscribers will have already seen an event that never durably persisted.
    This is a deliberate tradeoff for live progress visibility during long-running
    orchestration runs.
    """
    event = Event(
        run_id=run_id,
        agent_execution_id=agent_execution_id,
        event_type=event_type,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )
    db.add(event)
    await db.flush()

    try:
        await bus.publish(_serialize(event))
    except Exception:
        logger.exception("event bus publish failed for event %s (%s)", event.id, event_type)
    return event
