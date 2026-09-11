import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas import DecisionOut
from app.models.observability import Decision

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("/{decision_id}", response_model=DecisionOut)
async def get_decision(decision_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    decision = await db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return decision
