import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_or_404
from app.api.schemas import ToolExecutionOut
from app.models.observability import ToolExecution

router = APIRouter(prefix="/api/tool-executions", tags=["tool-executions"])


@router.get("/{tool_execution_id}", response_model=ToolExecutionOut)
async def get_tool_execution(tool_execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, ToolExecution, tool_execution_id, "tool execution not found")
