import uuid

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
    limit: int = Query(default=200, le=1000),
):
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

    result = await db.execute(stmt)
    return result.scalars().all()
