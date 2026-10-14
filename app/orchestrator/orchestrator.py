import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.registry import AGENT_REGISTRY
from app.config import get_settings
from app.decision.engine import reconcile
from app.events.bus import EventBus
from app.events.service import emit_event
from app.llm.base import LLMProvider
from app.models.observability import (
    Decision, OrchestrationRun, OrchestrationRunStatus, RunIteration,
)
from app.orchestrator.messages import send_message
from app.orchestrator.scheduler import FAILED, AgentOutcome, run_agents

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


def _default_session_factory(db: AsyncSession) -> Callable[[], AsyncSession]:
    """A factory on the request session's engine, for the per-agent sessions."""
    bind = getattr(db, "bind", None)  # only set when the session was created with a bind
    if bind is None:
        raise ValueError("session_factory is required when the session is not bound to an engine")
    return async_sessionmaker(bind, expire_on_commit=False)


async def _record_messages(db: AsyncSession, bus: EventBus, run_id, outcomes: dict[str, AgentOutcome]) -> None:
    """Each agent reports to the orchestrator, which forwards every result to the decision engine."""
    for outcome in outcomes.values():
        await send_message(
            db, bus=bus, run_id=run_id, sender=f"{outcome.agent_type}_AGENT", receiver="ORCHESTRATOR",
            message_type="RECOMMENDATION", payload=outcome.recommendation.model_dump(),
            context_id=outcome.context_id,
        )
    for outcome in outcomes.values():
        await send_message(
            db, bus=bus, run_id=run_id, sender="ORCHESTRATOR", receiver="DECISION_ENGINE",
            message_type="RECOMMENDATION",
            payload={"agent_type": outcome.agent_type, **outcome.recommendation.model_dump()},
            context_id=outcome.context_id,
        )


async def _run_iteration(
    db: AsyncSession,
    *,
    bus: EventBus,
    run: OrchestrationRun,
    iteration: RunIteration,
    llm_provider: LLMProvider,
    session_factory: Callable[[], AsyncSession],
) -> OrchestrationRun:
    """Run one iteration: agents (concurrently, as their dependencies allow) -> Decision.

    Every path ends with run.status == COMPLETED or FAILED (never left at RUNNING): agent
    failures (AgentRunError, reported by the scheduler) and everything else (context building,
    reconcile, final persistence) route to _fail_run.

    The run and iteration are committed before any agent starts: each agent runs on its own
    session (a session cannot be shared by concurrent tasks) and only sees committed rows.
    Each agent commits its own rows when it finishes, so a crash later in the iteration keeps
    the agents' work (and leaves the run RUNNING) instead of rolling everything back; the
    decision, messages and final status are committed together at the end.
    """
    await db.commit()
    try:
        previous_results = await _previous_decision_results(db, run.id)
        outcomes = await run_agents(
            registry=AGENT_REGISTRY, session_factory=session_factory, bus=bus, run_id=run.id,
            iteration_id=iteration.id, objective=iteration.objective, llm_provider=llm_provider,
            previous_results=previous_results, max_concurrency=get_settings().agent_concurrency,
        )
        failed = [agent_type for agent_type, outcome in outcomes.items() if outcome.status == FAILED]
        if failed:
            reason = "; ".join(f"{agent_type.lower()} agent failed" for agent_type in failed)
            return await _fail_run(db, bus, run, iteration, reason)

        network, fleet = outcomes.get("NETWORK"), outcomes.get("FLEET")
        if network is None or fleet is None:
            raise RuntimeError("the agent registry must include the NETWORK and FLEET agents")

        await _record_messages(db, bus, run.id, outcomes)

        decision_fields = reconcile(network.recommendation, fleet.recommendation)
        decision = Decision(
            run_id=run.id,
            iteration_id=iteration.id,
            agents_involved=[str(outcome.execution_id) for outcome in outcomes.values()],
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
    except Exception as exc:
        return await _fail_run(db, bus, run, iteration, f"unexpected orchestration failure: {exc}")


async def run_orchestration(
    db: AsyncSession,
    *,
    bus: EventBus,
    objective: str,
    llm_provider: LLMProvider,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> OrchestrationRun:
    """Create a run from `objective` and run its first iteration.

    `session_factory` makes the per-agent sessions; by default, sessions on `db`'s own engine.
    """
    session_factory = session_factory or _default_session_factory(db)
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
    return await _run_iteration(
        db, bus=bus, run=run, iteration=iteration, llm_provider=llm_provider,
        session_factory=session_factory,
    )


async def add_run_prompt(
    db: AsyncSession,
    *,
    bus: EventBus,
    run: OrchestrationRun,
    objective: str,
    llm_provider: LLMProvider,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> OrchestrationRun:
    """Run another iteration inside an existing run, prompted by `objective`.

    The run reopens (status RUNNING, completed_at cleared) for the duration, and the new
    iteration's agents see the run's earlier decisions as previous results.
    """
    session_factory = session_factory or _default_session_factory(db)
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
    return await _run_iteration(
        db, bus=bus, run=run, iteration=iteration, llm_provider=llm_provider,
        session_factory=session_factory,
    )
