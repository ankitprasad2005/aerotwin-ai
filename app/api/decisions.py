import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_or_404
from app.api.schemas import DecisionOut
from app.models.observability import Decision

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("/{decision_id}", response_model=DecisionOut)
async def get_decision(decision_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, Decision, decision_id, "decision not found")
