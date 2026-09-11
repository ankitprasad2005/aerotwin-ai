import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas import ToolExecutionOut
from app.models.observability import ToolExecution

router = APIRouter(prefix="/api/tool-executions", tags=["tool-executions"])


@router.get("/{tool_execution_id}", response_model=ToolExecutionOut)
async def get_tool_execution(tool_execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    execution = await db.get(ToolExecution, tool_execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="tool execution not found")
    return execution
