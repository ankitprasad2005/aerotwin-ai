import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas import EventOut
from app.models.observability import Event

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventOut])
async def list_events(
    db: AsyncSession = Depends(get_db),
    run_id: uuid.UUID | None = None,
    agent_execution_id: uuid.UUID | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    entity_type: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
):
    """List events, newest first, optionally filtered.

    `since` returns events created after the given timestamp (exclusive) — intended
    for a client that already has events up to some point and wants only what's new,
    e.g. polling as a fallback to the WebSocket stream. Ordering is newest-first,
    matching the live activity feed use case; a caller doing REST-backfill-then-
    WebSocket-tail should reverse the result before concatenating with live events.

    No offset/cursor pagination beyond `limit` yet — this returns "the latest N"
    matching filters, not a stable page. Revisit if a "load older events" UI need
    emerges.
    """
    stmt = select(Event).order_by(Event.created_at.desc()).limit(limit)
    if run_id is not None:
        stmt = stmt.where(Event.run_id == run_id)
    if agent_execution_id is not None:
        stmt = stmt.where(Event.agent_execution_id == agent_execution_id)
    if event_type is not None:
        stmt = stmt.where(Event.event_type == event_type)
    if severity is not None:
        stmt = stmt.where(Event.severity == severity)
    if entity_type is not None:
        stmt = stmt.where(Event.entity_type == entity_type)
    if since is not None:
        stmt = stmt.where(Event.created_at > since)

    result = await db.execute(stmt)
    return result.scalars().all()
