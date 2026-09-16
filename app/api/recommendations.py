import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.observability import Event


async def recommendations_by_execution(
    db: AsyncSession, agent_execution_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict]:
    """Each agent's structured recommendation (the parsed LLM output), keyed by agent execution id.

    Read from the `agent.completed` event the agent runner already emits, rather than a dedicated
    column: it carries the validated recommendation verbatim, so exposing it needs no schema change.
    Executions that haven't completed simply have no entry.
    """
    if not agent_execution_ids:
        return {}

    events = (
        await db.execute(
            select(Event)
            .where(
                Event.event_type == "agent.completed",
                Event.agent_execution_id.in_(agent_execution_ids),
            )
            .order_by(Event.created_at)
        )
    ).scalars().all()

    return {
        event.agent_execution_id: event.payload["recommendation"]
        for event in events
        if event.agent_execution_id is not None and isinstance(event.payload.get("recommendation"), dict)
    }
