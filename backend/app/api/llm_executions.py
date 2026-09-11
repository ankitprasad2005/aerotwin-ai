import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_or_404
from app.api.schemas import LLMExecutionOut
from app.models.observability import LLMExecution

router = APIRouter(prefix="/api/llm-executions", tags=["llm-executions"])


@router.get("/{llm_execution_id}", response_model=LLMExecutionOut)
async def get_llm_execution(llm_execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, LLMExecution, llm_execution_id, "llm execution not found")
