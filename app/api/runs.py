import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bus, get_db, get_llm_provider, get_or_404
from app.api.knowledge_graph import build_knowledge_graph
from app.api.recommendations import recommendations_by_execution
from app.api.schemas import (
    AgentExecutionOut,
    AgentMessageOut,
    DecisionOut,
    OrchestrationRunOut,
    RunCreate,
    RunDetailOut,
    RunIterationOut,
)
from app.events.bus import EventBus
from app.llm.base import LLMProvider
from app.models.observability import (
    AgentExecution, AgentMessage, ContextSnapshot, Decision, OrchestrationRun, RunIteration,
)
from app.orchestrator.orchestrator import add_run_prompt, run_orchestration

router = APIRouter(prefix="/api/runs", tags=["runs"])


async def _run_work(db: AsyncSession, run_id: uuid.UUID):
    """A run's iterations, agent executions (with recommendations) and decisions, in order."""
    iterations = (
        await db.execute(
            select(RunIteration).where(RunIteration.run_id == run_id).order_by(RunIteration.sequence)
        )
    ).scalars().all()
    executions = (
        await db.execute(
            select(AgentExecution).where(AgentExecution.run_id == run_id).order_by(AgentExecution.created_at)
        )
    ).scalars().all()
    decisions = (
        await db.execute(select(Decision).where(Decision.run_id == run_id).order_by(Decision.created_at))
    ).scalars().all()
    recommendations = await recommendations_by_execution(db, [e.id for e in executions])
    return iterations, executions, decisions, recommendations


def _execution_out(execution: AgentExecution, recommendations: dict) -> AgentExecutionOut:
    return AgentExecutionOut.model_validate(execution).model_copy(
        update={"recommendation": recommendations.get(execution.id)}
    )


@router.post("", response_model=OrchestrationRunOut)
async def create_run(
    body: RunCreate,
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_bus),
    llm_provider: LLMProvider = Depends(get_llm_provider),
):
    run = await run_orchestration(db, bus=bus, objective=body.objective, llm_provider=llm_provider)
    return run


@router.post("/{run_id}/prompts", response_model=OrchestrationRunOut)
async def create_run_prompt(
    run_id: uuid.UUID,
    body: RunCreate,
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_bus),
    llm_provider: LLMProvider = Depends(get_llm_provider),
):
    """Run another iteration inside an existing run, prompted by a new objective."""
    run = await get_or_404(db, OrchestrationRun, run_id, "run not found")
    return await add_run_prompt(db, bus=bus, run=run, objective=body.objective, llm_provider=llm_provider)


@router.get("", response_model=list[OrchestrationRunOut])
async def list_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrchestrationRun).order_by(OrchestrationRun.created_at.desc()))
    return result.scalars().all()


@router.get("/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await get_or_404(db, OrchestrationRun, run_id, "run not found")
    iterations, executions, decisions, recommendations = await _run_work(db, run_id)

    iterations_out = []
    for iteration in iterations:
        iteration_decisions = [d for d in decisions if d.iteration_id == iteration.id]
        iterations_out.append(
            RunIterationOut.model_validate(iteration).model_copy(
                update={
                    "agent_executions": [
                        _execution_out(e, recommendations) for e in executions if e.iteration_id == iteration.id
                    ],
                    "decision": DecisionOut.model_validate(iteration_decisions[-1]) if iteration_decisions else None,
                }
            )
        )

    return RunDetailOut(
        **OrchestrationRunOut.model_validate(run).model_dump(),
        agent_executions=[_execution_out(e, recommendations) for e in executions],
        decision=DecisionOut.model_validate(decisions[-1]) if decisions else None,
        iterations=iterations_out,
    )


@router.get("/{run_id}/messages", response_model=list[AgentMessageOut])
async def get_run_messages(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Inter-agent messages of a run, oldest first."""
    await get_or_404(db, OrchestrationRun, run_id, "run not found")
    result = await db.execute(
        select(AgentMessage).where(AgentMessage.run_id == run_id).order_by(AgentMessage.created_at)
    )
    return result.scalars().all()


@router.get("/{run_id}/graph")
async def get_run_graph(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await get_or_404(db, OrchestrationRun, run_id, "run not found")
    iterations, executions, decisions, _ = await _run_work(db, run_id)

    nodes = [{"id": "orchestrator", "type": "ORCHESTRATOR", "status": run.status, "iteration": None}]
    edges: list[dict] = []

    # One group of pipeline nodes per prompt. Runs made before iterations existed (or rows created
    # outside the orchestrator) have no iteration, so fall back to a single implicit group.
    groups = (
        [(i.sequence, i.status, [e for e in executions if e.iteration_id == i.id],
          [d for d in decisions if d.iteration_id == i.id]) for i in iterations]
        or [(1, run.status, list(executions), list(decisions))]
    )

    previous_tail = "orchestrator"
    for sequence, iteration_status, iteration_executions, iteration_decisions in groups:
        context_id = f"context_engine-{sequence}"
        decision_engine_id = f"decision_engine-{sequence}"
        decision = iteration_decisions[-1] if iteration_decisions else None
        # No agent executions and a failed iteration means it failed while building context.
        context_status = (
            "COMPLETED" if iteration_executions
            else ("FAILED" if iteration_status == "FAILED" else "WAITING")
        )
        nodes.append({"id": context_id, "type": "CONTEXT_ENGINE", "status": context_status, "iteration": sequence})
        edges.append({"source": previous_tail, "target": context_id})

        for execution in iteration_executions:
            node_id = f"agent-{execution.id}"
            nodes.append({
                "id": node_id, "type": f"{execution.agent_type}_AGENT", "status": execution.status,
                "agent_execution_id": str(execution.id), "iteration": sequence,
            })
            edges.append({"source": context_id, "target": node_id})
            edges.append({"source": node_id, "target": decision_engine_id})

        decision_status = "COMPLETED" if decision else ("RUNNING" if iteration_status == "RUNNING" else "BLOCKED")
        nodes.append({
            "id": decision_engine_id, "type": "DECISION_ENGINE", "status": decision_status, "iteration": sequence,
        })
        previous_tail = decision_engine_id
        if decision:
            final_id = f"final_decision-{sequence}"
            nodes.append({
                "id": final_id, "type": "FINAL_DECISION", "status": "COMPLETED",
                "decision_id": str(decision.id), "iteration": sequence,
            })
            edges.append({"source": decision_engine_id, "target": final_id})
            previous_tail = final_id

    return {"nodes": nodes, "edges": edges}


@router.get("/{run_id}/knowledge-graph")
async def get_run_knowledge_graph(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """What each of the run's agents knew, and what that knowledge produced."""
    await get_or_404(db, OrchestrationRun, run_id, "run not found")
    iterations, executions, decisions, recommendations = await _run_work(db, run_id)
    sequence_by_iteration_id = {i.id: i.sequence for i in iterations}

    snapshots = (
        await db.execute(
            select(ContextSnapshot)
            .where(ContextSnapshot.agent_execution_id.in_([e.id for e in executions] or [uuid.uuid4()]))
            .order_by(ContextSnapshot.created_at)
        )
    ).scalars().all()
    context_by_execution = {snapshot.agent_execution_id: snapshot.payload for snapshot in snapshots}

    return build_knowledge_graph(
        agents=[
            {
                "execution_id": str(execution.id),
                "agent_type": execution.agent_type,
                "status": execution.status,
                "iteration": sequence_by_iteration_id.get(execution.iteration_id),
                "context": context_by_execution.get(execution.id) or {},
                "recommendation": recommendations.get(execution.id),
            }
            for execution in executions
        ],
        decisions=[
            {
                "decision_id": str(decision.id),
                "iteration": sequence_by_iteration_id.get(decision.iteration_id),
                "summary": decision.summary,
                "risk": (decision.validation_result or {}).get("risk"),
                "expected_profit_impact": decision.expected_profit_impact,
            }
            for decision in decisions
        ],
    )
