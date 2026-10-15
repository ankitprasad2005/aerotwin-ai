import asyncio
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runner import AgentRunError, block_agent, run_agent
from app.agents.spec import AgentSpec
from app.context.engine import build_context_payload
from app.events.bus import EventBus
from app.llm.base import LLMProvider
from app.models.observability import AgentExecutionStatus, ContextSnapshot

COMPLETED = AgentExecutionStatus.COMPLETED.value
FAILED = AgentExecutionStatus.FAILED.value


@dataclass
class AgentOutcome:
    agent_type: str
    status: str  # COMPLETED or FAILED (agents that never started are recorded as BLOCKED rows only)
    execution_id: uuid.UUID
    context_id: uuid.UUID | None = None
    recommendation: BaseModel | None = None
    error: str | None = None
    evidence: list[dict] = field(default_factory=list)  # the evidence items in the agent's context


def _dependency_results(spec: AgentSpec, outcomes: dict[str, AgentOutcome]) -> list[dict]:
    return [{"agent_type": dep, **outcomes[dep].recommendation.model_dump()} for dep in spec.depends_on]


async def run_agents(
    *,
    registry: Mapping[str, AgentSpec],
    session_factory: Callable[[], AsyncSession],
    bus: EventBus,
    run_id: uuid.UUID,
    iteration_id: uuid.UUID,
    objective: str,
    llm_provider: LLMProvider,
    previous_results: list[dict],
    max_concurrency: int,
) -> dict[str, AgentOutcome]:
    """Run every agent in `registry`, starting each as soon as the agents it depends on completed.

    Ready agents run concurrently (at most `max_concurrency` tasks exist at once, so nothing queued can start after a failure), each on its own session
    that commits when the agent finishes, so its rows are durable whatever happens to siblings.
    An agent failing with AgentRunError stops new starts; running agents finish, and every agent
    that never started is recorded as BLOCKED. Any other exception cancels the remaining agents
    and propagates. Returns outcomes for the agents that ran, ordered like `registry`.
    """
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be >= 1")

    outcomes: dict[str, AgentOutcome] = {}
    pending = list(registry)
    running: dict[asyncio.Task, str] = {}

    async def run_one(spec: AgentSpec, results: list[dict]) -> AgentOutcome:
        async with session_factory() as session:
            try:
                context = await build_context_payload(
                    session, objective=objective, spec=spec, previous_results=results
                )
                execution, recommendation = await run_agent(
                    session, bus=bus, run_id=run_id, iteration_id=iteration_id, spec=spec,
                    context_payload=context, llm_provider=llm_provider,
                )
                context_id = (
                    await session.execute(
                        select(ContextSnapshot.id).where(ContextSnapshot.agent_execution_id == execution.id)
                    )
                ).scalar_one_or_none()
                await session.commit()
            except AgentRunError as exc:
                await session.commit()  # keep the FAILED execution and its events
                return AgentOutcome(spec.agent_type, FAILED, exc.agent_execution_id, error=str(exc))
            evidence = context.get("evidence")
            return AgentOutcome(
                spec.agent_type, COMPLETED, execution.id, context_id, recommendation,
                evidence=evidence if isinstance(evidence, list) else [],
            )

    def has_failed() -> bool:
        return any(outcome.status == FAILED for outcome in outcomes.values())

    def is_ready(agent_type: str) -> bool:
        return all(
            dep in outcomes and outcomes[dep].status == COMPLETED for dep in registry[agent_type].depends_on
        )

    try:
        while True:
            if not has_failed():
                for agent_type in [t for t in pending if is_ready(t)]:
                    if len(running) >= max_concurrency:
                        break  # a slot frees up when a running agent finishes; start it then
                    pending.remove(agent_type)
                    spec = registry[agent_type]
                    task = asyncio.create_task(
                        run_one(spec, [*previous_results, *_dependency_results(spec, outcomes)])
                    )
                    running[task] = agent_type
            if not running:
                break
            done, _ = await asyncio.wait(set(running), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                outcomes[running.pop(task)] = task.result()
    except BaseException:
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)
        raise

    if pending:
        failed = [agent_type for agent_type, outcome in outcomes.items() if outcome.status == FAILED]
        if not failed:
            raise RuntimeError(f"agents can never start (unmet dependencies): {', '.join(pending)}")
        async with session_factory() as session:
            for agent_type in pending:
                await block_agent(
                    session, bus=bus, run_id=run_id, iteration_id=iteration_id,
                    spec=registry[agent_type], blocked_by=failed,
                )
            await session.commit()

    return {agent_type: outcomes[agent_type] for agent_type in registry if agent_type in outcomes}
