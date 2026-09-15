import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bus, get_db, get_llm_provider, get_or_404
from app.api.schemas import AgentExecutionOut, DecisionOut, OrchestrationRunOut, RunCreate, RunDetailOut
from app.events.bus import EventBus
from app.llm.base import LLMProvider
from app.models.observability import AgentExecution, Decision, OrchestrationRun
from app.orchestrator.orchestrator import run_orchestration

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=OrchestrationRunOut)
async def create_run(
    body: RunCreate,
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_bus),
    llm_provider: LLMProvider = Depends(get_llm_provider),
):
    run = await run_orchestration(db, bus=bus, objective=body.objective, llm_provider=llm_provider)
    return run


@router.get("", response_model=list[OrchestrationRunOut])
async def list_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrchestrationRun).order_by(OrchestrationRun.created_at.desc()))
    return result.scalars().all()


@router.get("/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await get_or_404(db, OrchestrationRun, run_id, "run not found")

    executions = (
        await db.execute(
            select(AgentExecution).where(AgentExecution.run_id == run_id).order_by(AgentExecution.created_at)
        )
    ).scalars().all()
    decision = (await db.execute(select(Decision).where(Decision.run_id == run_id))).scalars().first()

    return RunDetailOut(
        **OrchestrationRunOut.model_validate(run).model_dump(),
        agent_executions=[AgentExecutionOut.model_validate(e) for e in executions],
        decision=DecisionOut.model_validate(decision) if decision else None,
    )


@router.get("/{run_id}/graph")
async def get_run_graph(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await get_or_404(db, OrchestrationRun, run_id, "run not found")

    executions = (
        await db.execute(
            select(AgentExecution).where(AgentExecution.run_id == run_id).order_by(AgentExecution.created_at)
        )
    ).scalars().all()
    decision = (await db.execute(select(Decision).where(Decision.run_id == run_id))).scalars().first()

    nodes = [
        {"id": "orchestrator", "type": "ORCHESTRATOR", "status": run.status},
        {"id": "context_engine", "type": "CONTEXT_ENGINE", "status": "COMPLETED" if executions else "WAITING"},
    ]
    edges = [{"source": "orchestrator", "target": "context_engine"}]

    for execution in executions:
        node_id = f"agent-{execution.id}"
        nodes.append(
            {
                "id": node_id, "type": f"{execution.agent_type}_AGENT", "status": execution.status,
                "agent_execution_id": str(execution.id),
            }
        )
        edges.append({"source": "context_engine", "target": node_id})

    decision_status = "COMPLETED" if decision else ("RUNNING" if run.status == "RUNNING" else "BLOCKED")
    nodes.append({"id": "decision_engine", "type": "DECISION_ENGINE", "status": decision_status})
    for execution in executions:
        edges.append({"source": f"agent-{execution.id}", "target": "decision_engine"})

    if decision:
        nodes.append(
            {"id": "final_decision", "type": "FINAL_DECISION", "status": "COMPLETED", "decision_id": str(decision.id)}
        )
        edges.append({"source": "decision_engine", "target": "final_decision"})

    return {"nodes": nodes, "edges": edges}
