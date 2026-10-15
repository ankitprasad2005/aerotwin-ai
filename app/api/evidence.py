import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_or_404
from app.api.recommendations import recommendations_by_execution
from app.models.observability import AgentExecution, ContextSnapshot, OrchestrationRun, RunIteration

router = APIRouter(prefix="/api/runs", tags=["evidence"])


def _string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


@router.get("/{run_id}/evidence")
async def get_run_evidence(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[dict]:
    """The external evidence each agent of the run saw, and the evidence ids it cited, in execution order."""
    await get_or_404(db, OrchestrationRun, run_id, "run not found")
    executions = (
        await db.execute(
            select(AgentExecution).where(AgentExecution.run_id == run_id).order_by(AgentExecution.created_at)
        )
    ).scalars().all()
    execution_ids = [e.id for e in executions]
    if not execution_ids:
        return []

    sequences = {
        iteration.id: iteration.sequence
        for iteration in (
            await db.execute(select(RunIteration).where(RunIteration.run_id == run_id))
        ).scalars()
    }
    snapshots = (
        await db.execute(
            select(ContextSnapshot)
            .where(ContextSnapshot.agent_execution_id.in_(execution_ids))
            .order_by(ContextSnapshot.created_at)
        )
    ).scalars().all()
    context_by_execution = {snapshot.agent_execution_id: snapshot.payload for snapshot in snapshots}
    recommendations = await recommendations_by_execution(db, execution_ids)

    out = []
    for execution in executions:
        context = context_by_execution.get(execution.id) or {}
        evidence = context.get("evidence")
        out.append({
            "agent_execution_id": str(execution.id),
            "agent_type": execution.agent_type,
            "iteration": sequences.get(execution.iteration_id),
            "evidence": evidence if isinstance(evidence, list) else [],
            "evidence_unavailable": _string_list(context.get("evidence_unavailable")),
            "cited_sources": _string_list((recommendations.get(execution.id) or {}).get("cited_sources")),
        })
    return out
