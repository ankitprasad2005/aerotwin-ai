import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.fleet_agent import FLEET_AGENT_SPEC
from app.agents.network_agent import NETWORK_AGENT_SPEC
from app.agents.runner import AgentRunError, run_agent
from app.context.engine import build_context_payload
from app.decision.engine import reconcile
from app.events.bus import EventBus
from app.events.service import emit_event
from app.llm.base import LLMProvider
from app.models.observability import AgentMessage, Decision, OrchestrationRun, OrchestrationRunStatus

logger = logging.getLogger(__name__)


async def _fail_run(db: AsyncSession, bus: EventBus, run: OrchestrationRun, reason: str) -> OrchestrationRun:
    """Mark run FAILED, emit orchestration.failed, and commit.

    Defensive against the session already being in a bad state: if the flush/commit
    here itself fails, roll back and log rather than letting the failure escape
    uncaught (the caller still gets a run object with status=FAILED in memory,
    even though nothing was durably persisted in that edge case).
    """
    run.status = OrchestrationRunStatus.FAILED.value
    try:
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="orchestration.failed", run_id=run.id,
            agent_execution_id=None, payload={"reason": reason}, severity="ERROR",
        )
        await db.commit()
    except Exception:
        logger.exception("failed to persist orchestration.failed state for run %s", run.id)
        await db.rollback()
    return run


async def run_orchestration(
    db: AsyncSession,
    *,
    bus: EventBus,
    objective: str,
    llm_provider: LLMProvider,
) -> OrchestrationRun:
    """Run the full pipeline: context -> Network agent -> Fleet agent -> Decision.

    Every path through this function ends with run.status == COMPLETED or FAILED
    (never left at RUNNING): the two run_agent() calls are caught individually
    (AgentRunError) so failure reasons are specific ("network agent failed" /
    "fleet agent failed"), and everything else (context building, reconcile,
    final persistence) is caught by an outer handler that also routes to
    _fail_run with a generic reason, so no exception escapes uncaught.

    Single-commit-per-run is intentional for Phase 1: nothing is durably persisted
    until the very end, so a crash mid-run loses all progress from that run (the
    live event broadcast some subscribers may have already seen won't be confirmed
    by a later DB query). Run resumability/partial-commit is out of scope for Phase 1.
    """
    run = OrchestrationRun(objective=objective, status=OrchestrationRunStatus.RUNNING.value)
    db.add(run)
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="orchestration.started", run_id=run.id,
        agent_execution_id=None, payload={"objective": objective},
    )

    try:
        network_context = await build_context_payload(db, objective=objective, agent_type="NETWORK")
        try:
            network_execution, network_recommendation = await run_agent(
                db, bus=bus, run_id=run.id, spec=NETWORK_AGENT_SPEC,
                context_payload=network_context, llm_provider=llm_provider,
            )
        except AgentRunError:
            return await _fail_run(db, bus, run, "network agent failed")

        # TODO(context linkage): AgentMessage.context_id is None because run_agent()
        # doesn't currently return the ContextSnapshot id it creates internally.
        db.add(AgentMessage(
            run_id=run.id, context_id=None, sender="NETWORK_AGENT", receiver="ORCHESTRATOR",
            message_type="RECOMMENDATION", payload=network_recommendation.model_dump(),
        ))
        await db.flush()

        fleet_context = await build_context_payload(
            db, objective=objective, agent_type="FLEET",
            previous_results=[{"agent_type": "NETWORK", **network_recommendation.model_dump()}],
        )
        try:
            fleet_execution, fleet_recommendation = await run_agent(
                db, bus=bus, run_id=run.id, spec=FLEET_AGENT_SPEC,
                context_payload=fleet_context, llm_provider=llm_provider,
            )
        except AgentRunError:
            return await _fail_run(db, bus, run, "fleet agent failed")

        # TODO(context linkage): same limitation as above.
        db.add(AgentMessage(
            run_id=run.id, context_id=None, sender="FLEET_AGENT", receiver="ORCHESTRATOR",
            message_type="RECOMMENDATION", payload=fleet_recommendation.model_dump(),
        ))
        await db.flush()

        decision_fields = reconcile(network_recommendation, fleet_recommendation)
        decision = Decision(
            run_id=run.id,
            agents_involved=[str(network_execution.id), str(fleet_execution.id)],
            **decision_fields,
        )
        db.add(decision)
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="decision.created", run_id=run.id, agent_execution_id=None,
            payload={"decision_id": str(decision.id), "summary": decision.summary},
        )

        run.status = OrchestrationRunStatus.COMPLETED.value
        run.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await emit_event(
            db, bus=bus, event_type="orchestration.completed", run_id=run.id,
            agent_execution_id=None, payload={"decision_id": str(decision.id)},
        )
        await db.commit()
        return run
    except AgentRunError:
        raise  # already handled by the inner try/excepts above; re-raise is unreachable but explicit
    except Exception as exc:
        return await _fail_run(db, bus, run, f"unexpected orchestration failure: {exc}")
