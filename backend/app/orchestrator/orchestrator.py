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


async def _fail_run(db: AsyncSession, bus: EventBus, run: OrchestrationRun, reason: str) -> OrchestrationRun:
    """Mark `run` FAILED and emit `orchestration.failed`, then commit.

    Safe to call right after catching an AgentRunError: the LLM-failure path in
    run_agent is a pure Python exception with no DB involvement, and the
    tool-failure path is wrapped in db.begin_nested() inside run_tool, so in
    neither case is the outer session left in a poisoned/pending-rollback state.
    (Verified against the existing run_agent failure-path tests in
    tests/test_agent_runner.py, which continue to query/flush the same session
    after catching AgentRunError.)
    """
    run.status = OrchestrationRunStatus.FAILED.value
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="orchestration.failed", run_id=run.id,
        agent_execution_id=None, payload={"reason": reason}, severity="ERROR",
    )
    await db.commit()
    return run


async def run_orchestration(
    db: AsyncSession,
    *,
    bus: EventBus,
    objective: str,
    llm_provider: LLMProvider,
) -> OrchestrationRun:
    """Run the full pipeline: context -> network agent -> fleet agent -> decision reconciliation.

    Every path either reaches OrchestrationRunStatus.COMPLETED or FAILED before
    returning; run.status never remains RUNNING.
    """
    run = OrchestrationRun(objective=objective, status=OrchestrationRunStatus.RUNNING.value)
    db.add(run)
    await db.flush()
    await emit_event(
        db, bus=bus, event_type="orchestration.started", run_id=run.id,
        agent_execution_id=None, payload={"objective": objective},
    )

    network_context = await build_context_payload(db, objective=objective, agent_type="NETWORK")
    try:
        network_execution, network_recommendation = await run_agent(
            db, bus=bus, run_id=run.id, spec=NETWORK_AGENT_SPEC,
            context_payload=network_context, llm_provider=llm_provider,
        )
    except AgentRunError as exc:
        return await _fail_run(db, bus, run, f"network agent failed: {exc}")

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
    except AgentRunError as exc:
        return await _fail_run(db, bus, run, f"fleet agent failed: {exc}")

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
