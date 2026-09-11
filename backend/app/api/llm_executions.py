import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas import LLMExecutionOut
from app.models.observability import LLMExecution

router = APIRouter(prefix="/api/llm-executions", tags=["llm-executions"])


@router.get("/{llm_execution_id}", response_model=LLMExecutionOut)
async def get_llm_execution(llm_execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    execution = await db.get(LLMExecution, llm_execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="llm execution not found")
    return execution
