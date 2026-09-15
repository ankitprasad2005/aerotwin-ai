import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_or_404
from app.api.schemas import (
    AgentExecutionDetailOut,
    AgentExecutionOut,
    ContextSnapshotOut,
    LLMExecutionOut,
    ToolExecutionOut,
)
from app.models.observability import AgentExecution, ContextSnapshot, LLMExecution, ToolExecution

router = APIRouter(prefix="/api/agent-executions", tags=["agent-executions"])


@router.get("/{agent_execution_id}", response_model=AgentExecutionDetailOut)
async def get_agent_execution(agent_execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    execution = await get_or_404(db, AgentExecution, agent_execution_id, "agent execution not found")

    snapshot = (
        await db.execute(
            select(ContextSnapshot)
            .where(ContextSnapshot.agent_execution_id == agent_execution_id)
            .order_by(ContextSnapshot.created_at.desc())
        )
    ).scalars().first()
    llm_execution = (
        await db.execute(
            select(LLMExecution)
            .where(LLMExecution.agent_execution_id == agent_execution_id)
            .order_by(LLMExecution.created_at.desc())
        )
    ).scalars().first()
    tool_executions = (
        await db.execute(
            select(ToolExecution)
            .where(ToolExecution.agent_execution_id == agent_execution_id)
            .order_by(ToolExecution.created_at)
        )
    ).scalars().all()

    return AgentExecutionDetailOut(
        **AgentExecutionOut.model_validate(execution).model_dump(),
        context_snapshot=ContextSnapshotOut.model_validate(snapshot) if snapshot else None,
        llm_execution=LLMExecutionOut.model_validate(llm_execution) if llm_execution else None,
        tool_executions=[ToolExecutionOut.model_validate(t) for t in tool_executions],
    )
