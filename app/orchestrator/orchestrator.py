import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.fleet_agent import FLEET_AGENT_SPEC
from app.agents.network_agent import NETWORK_AGENT_SPEC
from app.agents.runner import AgentRunError, run_agent
from app.context.engine import build_context_payload
from app.decision.engine import reconcile
from app.events.bus import EventBus
from app.events.service import emit_event
from app.llm.base import LLMProvider
from app.models.observability import (
    AgentMessage, Decision, OrchestrationRun, OrchestrationRunStatus, RunIteration,
)

logger = logging.getLogger(__name__)


async def _fail_run(
    db: AsyncSession, bus: EventBus, run: OrchestrationRun, iteration: RunIteration, reason: str
) -> OrchestrationRun:
    """Mark run and iteration FAILED, emit orchestration.failed, and commit.

    Defensive against the session already being in a bad state: if the flush/commit
    here itself fails, roll back and log rather than letting the failure escape
    uncaught (the caller still gets a run object with status=FAILED in memory,
    even though nothing was durably persisted in that edge case).
    """
    failed_at = datetime.now(timezone.utc)
    run.status = OrchestrationRunStatus.FAILED.value
    run.completed_at = failed_at
    iteration.status = OrchestrationRunStatus.FAILED.value
    iteration.completed_at = failed_at
    try:
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="orchestration.failed", run_id=run.id,
            agent_execution_id=None, payload={"reason": reason, "iteration": iteration.sequence},
            severity="ERROR",
        )
        await db.commit()
    except Exception:
        logger.exception("failed to persist orchestration.failed state for run %s", run.id)
        await db.rollback()
    return run


async def _previous_decision_results(db: AsyncSession, run_id) -> list[dict]:
    """Decisions already made in this run, shaped as previous agent results.

    A follow-up prompt's agents receive these so they build on what the run has already decided
    (and don't re-recommend a change that is already on the table).
    """
    decisions = (
        await db.execute(select(Decision).where(Decision.run_id == run_id).order_by(Decision.created_at))
    ).scalars().all()
    return [
        {
            "source": "PREVIOUS_DECISION",
            "summary": decision.summary,
            "expected_profit_impact": decision.expected_profit_impact,
            "risk": (decision.validation_result or {}).get("risk"),
        }
        for decision in decisions
    ]


async def _run_iteration(
    db: AsyncSession,
    *,
    bus: EventBus,
    run: OrchestrationRun,
    iteration: RunIteration,
    llm_provider: LLMProvider,
) -> OrchestrationRun:
    """Run one iteration's pipeline: context -> Network agent -> Fleet agent -> Decision.

    Every path ends with run.status == COMPLETED or FAILED (never left at RUNNING): the two
    run_agent() calls are caught individually (AgentRunError) so failure reasons are specific
    ("network agent failed" / "fleet agent failed"), and everything else (context building,
    reconcile, final persistence) is caught by an outer handler that also routes to _fail_run
    with a generic reason, so no exception escapes uncaught.

    Single-commit-per-iteration is intentional for Phase 1: nothing from this iteration is
    durably persisted until the end, so a crash mid-iteration loses its progress (the live event
    broadcast some subscribers may have already seen won't be confirmed by a later DB query).
    """
    objective = iteration.objective
    try:
        previous_results = await _previous_decision_results(db, run.id)
        network_context = await build_context_payload(
            db, objective=objective, agent_type="NETWORK", previous_results=previous_results
        )
        try:
            network_execution, network_recommendation = await run_agent(
                db, bus=bus, run_id=run.id, iteration_id=iteration.id, spec=NETWORK_AGENT_SPEC,
                context_payload=network_context, llm_provider=llm_provider,
            )
        except AgentRunError:
            return await _fail_run(db, bus, run, iteration, "network agent failed")

        # TODO(context linkage): AgentMessage.context_id is None because run_agent()
        # doesn't currently return the ContextSnapshot id it creates internally.
        db.add(AgentMessage(
            run_id=run.id, context_id=None, sender="NETWORK_AGENT", receiver="ORCHESTRATOR",
            message_type="RECOMMENDATION", payload=network_recommendation.model_dump(),
        ))
        await db.flush()

        fleet_context = await build_context_payload(
            db, objective=objective, agent_type="FLEET",
            previous_results=[*previous_results, {"agent_type": "NETWORK", **network_recommendation.model_dump()}],
        )
        try:
            fleet_execution, fleet_recommendation = await run_agent(
                db, bus=bus, run_id=run.id, iteration_id=iteration.id, spec=FLEET_AGENT_SPEC,
                context_payload=fleet_context, llm_provider=llm_provider,
            )
        except AgentRunError:
            return await _fail_run(db, bus, run, iteration, "fleet agent failed")

        # TODO(context linkage): same limitation as above.
        db.add(AgentMessage(
            run_id=run.id, context_id=None, sender="FLEET_AGENT", receiver="ORCHESTRATOR",
            message_type="RECOMMENDATION", payload=fleet_recommendation.model_dump(),
        ))
        await db.flush()

        decision_fields = reconcile(network_recommendation, fleet_recommendation)
        decision = Decision(
            run_id=run.id,
            iteration_id=iteration.id,
            agents_involved=[str(network_execution.id), str(fleet_execution.id)],
            **decision_fields,
        )
        db.add(decision)
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="decision.created", run_id=run.id, agent_execution_id=None,
            payload={
                "decision_id": str(decision.id), "summary": decision.summary,
                "iteration": iteration.sequence,
            },
        )

        completed_at = datetime.now(timezone.utc)
        iteration.status = OrchestrationRunStatus.COMPLETED.value
        iteration.completed_at = completed_at
        run.status = OrchestrationRunStatus.COMPLETED.value
        run.completed_at = completed_at
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="orchestration.completed", run_id=run.id,
            agent_execution_id=None,
            payload={"decision_id": str(decision.id), "iteration": iteration.sequence},
        )
        await db.commit()
        return run
    except AgentRunError:
        raise  # already handled by the inner try/excepts above; re-raise is unreachable but explicit
    except Exception as exc:
        return await _fail_run(db, bus, run, iteration, f"unexpected orchestration failure: {exc}")


async def run_orchestration(
    db: AsyncSession,
    *,
    bus: EventBus,
    objective: str,
    llm_provider: LLMProvider,
) -> OrchestrationRun:
    """Create a run from `objective` and run its first iteration."""
    run = OrchestrationRun(objective=objective, status=OrchestrationRunStatus.RUNNING.value)
    db.add(run)
    await db.flush()
    iteration = RunIteration(
        run_id=run.id, sequence=1, objective=objective, status=OrchestrationRunStatus.RUNNING.value
    )
    db.add(iteration)
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="orchestration.started", run_id=run.id,
        agent_execution_id=None, payload={"objective": objective, "iteration": 1},
    )
    return await _run_iteration(db, bus=bus, run=run, iteration=iteration, llm_provider=llm_provider)


async def add_run_prompt(
    db: AsyncSession,
    *,
    bus: EventBus,
    run: OrchestrationRun,
    objective: str,
    llm_provider: LLMProvider,
) -> OrchestrationRun:
    """Run another iteration inside an existing run, prompted by `objective`.

    The run reopens (status RUNNING, completed_at cleared) for the duration, and the new
    iteration's agents see the run's earlier decisions as previous results.
    """
    last_sequence = (
        await db.execute(select(func.max(RunIteration.sequence)).where(RunIteration.run_id == run.id))
    ).scalar() or 0
    iteration = RunIteration(
        run_id=run.id, sequence=last_sequence + 1, objective=objective,
        status=OrchestrationRunStatus.RUNNING.value,
    )
    db.add(iteration)
    run.status = OrchestrationRunStatus.RUNNING.value
    run.completed_at = None
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="iteration.started", run_id=run.id, agent_execution_id=None,
        payload={"objective": objective, "iteration": iteration.sequence},
    )
    return await _run_iteration(db, bus=bus, run=run, iteration=iteration, llm_provider=llm_provider)
