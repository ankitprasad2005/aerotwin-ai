import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.schemas import NetworkRecommendation
from app.agents.spec import AgentSpec
from app.events.bus import EventBus
from app.llm.base import LLMProviderError
from app.llm.fake_provider import FakeLLMProvider
from app.models.observability import (
    AgentExecution, AgentExecutionStatus, Event, OrchestrationRun, OrchestrationRunStatus, RunIteration,
)
from app.orchestrator import scheduler as scheduler_module
from app.orchestrator.scheduler import run_agents

CANNED = {
    "route": "BOM-DEL", "action": "INCREASE_FREQUENCY", "expected_profit_impact": 125000.0,
    "expected_revenue_impact": 300000.0, "expected_cost_impact": 175000.0, "confidence": 0.82,
    "risks": ["fuel price volatility"], "reasoning": "Demand exceeds current capacity.",
}
COMPLETED = AgentExecutionStatus.COMPLETED.value
FAILED = AgentExecutionStatus.FAILED.value
BLOCKED = AgentExecutionStatus.BLOCKED.value


async def _tool(db):
    return {"routes": []}


def _spec(name, *deps):
    return AgentSpec(
        agent_type=name, task_description=f"task-{name}", system_instructions="sys", tool_name="fake_tool",
        tool_fn=_tool, output_schema=NetworkRecommendation, entities_key="routes", depends_on=tuple(deps),
    )


def _registry(*specs):
    return {spec.agent_type: spec for spec in specs}


class _ProbeProvider:
    """Fake LLM whose per-task behaviour (barrier, delay, failure, hang) makes concurrency observable."""

    def __init__(self, *, barrier=0, delay=0.0, fail_tasks=(), hang_tasks=()):
        self._inner = FakeLLMProvider(canned_response=CANNED)
        self._barrier = barrier
        self._entered = 0
        self._all_entered = asyncio.Event()
        self._delay = delay
        self._fail_tasks = set(fail_tasks)
        self._hang_tasks = set(hang_tasks)
        self.order: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0
        self.cancelled: list[str] = []
        self.hanging = asyncio.Event()

    @property
    def calls(self):
        return self._inner.calls

    async def complete(self, *, system_instructions, context, task, available_tools, output_schema):
        self.order.append(("enter", task))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self._barrier:
                self._entered += 1
                if self._entered >= self._barrier:
                    self._all_entered.set()
                # A serial scheduler never reaches the barrier: the timeout then fails the agent.
                await asyncio.wait_for(self._all_entered.wait(), timeout=2)
            if task in self._hang_tasks:
                self.hanging.set()
                await asyncio.Event().wait()
            if self._delay:
                await asyncio.sleep(self._delay)
            if task in self._fail_tasks:
                raise LLMProviderError("forced failure")
            return await self._inner.complete(
                system_instructions=system_instructions, context=context, task=task,
                available_tools=available_tools, output_schema=output_schema,
            )
        except asyncio.CancelledError:
            self.cancelled.append(task)
            raise
        finally:
            self.active -= 1
            self.order.append(("exit", task))


def _factory(db_session):
    return async_sessionmaker(db_session.bind, expire_on_commit=False)


async def _make_run(db_session):
    run = OrchestrationRun(objective="obj", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()
    iteration = RunIteration(
        run_id=run.id, sequence=1, objective="obj", status=OrchestrationRunStatus.RUNNING.value
    )
    db_session.add(iteration)
    await db_session.commit()  # agents use other sessions, which only see committed rows
    return run, iteration


def _kwargs(db_session, run, iteration, registry, provider, **overrides):
    kwargs = dict(
        registry=registry, session_factory=_factory(db_session), bus=EventBus(), run_id=run.id,
        iteration_id=iteration.id, objective="obj", llm_provider=provider, previous_results=[],
        max_concurrency=4,
    )
    kwargs.update(overrides)
    return kwargs


async def _execute(db_session, registry, provider, **overrides):
    run, iteration = await _make_run(db_session)
    outcomes = await run_agents(**_kwargs(db_session, run, iteration, registry, provider, **overrides))
    return run, outcomes


async def _executions_by_type(db_session, run):
    rows = (await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))).scalars().all()
    return {row.agent_type: row for row in rows}


async def test_independent_agents_run_concurrently(db_session):
    provider = _ProbeProvider(barrier=2)

    _, outcomes = await _execute(db_session, _registry(_spec("A"), _spec("B")), provider)

    assert [o.status for o in outcomes.values()] == [COMPLETED, COMPLETED]
    assert provider.max_active == 2


async def test_dependent_agent_starts_only_after_its_dependency_finishes(db_session):
    provider = _ProbeProvider()

    _, outcomes = await _execute(db_session, _registry(_spec("A"), _spec("B", "A")), provider)

    assert provider.order == [("enter", "task-A"), ("exit", "task-A"), ("enter", "task-B"), ("exit", "task-B")]
    assert outcomes["B"].status == COMPLETED


async def test_dependent_agent_receives_its_dependencys_recommendation_only(db_session):
    provider = _ProbeProvider()
    registry = _registry(_spec("A"), _spec("B"), _spec("C", "A"))

    await _execute(db_session, registry, provider)

    context_for_c = next(call["context"] for call in provider.calls if call["task"] == "task-C")
    assert [r["agent_type"] for r in context_for_c["previous_agent_results"]] == ["A"]
    assert context_for_c["previous_agent_results"][0]["route"] == "BOM-DEL"


async def test_base_previous_results_come_before_dependency_results(db_session):
    provider = _ProbeProvider()
    base = [{"source": "PREVIOUS_DECISION", "summary": "earlier"}]

    await _execute(db_session, _registry(_spec("A"), _spec("B", "A")), provider, previous_results=base)

    context_for_b = next(call["context"] for call in provider.calls if call["task"] == "task-B")
    assert context_for_b["previous_agent_results"][0] == base[0]
    assert context_for_b["previous_agent_results"][1]["agent_type"] == "A"


async def test_diamond_waits_for_every_dependency(db_session):
    provider = _ProbeProvider(barrier=2)  # barrier applies to the first two entrants only
    registry = _registry(_spec("A"), _spec("B"), _spec("C", "A", "B"))

    _, outcomes = await _execute(db_session, registry, provider)

    order = provider.order
    assert order.index(("enter", "task-C")) > order.index(("exit", "task-A"))
    assert order.index(("enter", "task-C")) > order.index(("exit", "task-B"))
    assert list(outcomes) == ["A", "B", "C"]


async def test_outcomes_are_ordered_by_registry_not_completion(db_session):
    provider = _ProbeProvider()

    _, outcomes = await _execute(db_session, _registry(_spec("A"), _spec("B"), _spec("C")), provider)

    assert list(outcomes) == ["A", "B", "C"]


async def test_outcome_carries_execution_context_and_recommendation(db_session):
    run, outcomes = await _execute(db_session, _registry(_spec("A")), _ProbeProvider())

    outcome = outcomes["A"]
    executions = await _executions_by_type(db_session, run)
    assert outcome.execution_id == executions["A"].id
    assert outcome.context_id is not None
    assert outcome.recommendation.route == "BOM-DEL"
    assert outcome.error is None


async def test_concurrency_cap_of_one_serialises_independent_agents(db_session):
    provider = _ProbeProvider(delay=0.02)

    await _execute(db_session, _registry(_spec("A"), _spec("B"), _spec("C")), provider, max_concurrency=1)

    assert provider.max_active == 1


async def test_concurrency_cap_of_two_limits_three_ready_agents(db_session):
    # The barrier forces the first two to overlap (>= 2); the cap forbids a third (<= 2).
    provider = _ProbeProvider(barrier=2, delay=0.02)

    _, outcomes = await _execute(
        db_session, _registry(_spec("A"), _spec("B"), _spec("C")), provider, max_concurrency=2
    )

    assert provider.max_active == 2
    assert all(o.status == COMPLETED for o in outcomes.values())


async def test_concurrency_cap_below_one_is_rejected(db_session):
    run, iteration = await _make_run(db_session)
    with pytest.raises(ValueError, match="max_concurrency"):
        await run_agents(**_kwargs(db_session, run, iteration, _registry(_spec("A")), _ProbeProvider(), max_concurrency=0))


async def test_failure_blocks_dependents_but_running_siblings_finish(db_session):
    provider = _ProbeProvider(barrier=2, fail_tasks={"task-A"})
    registry = _registry(_spec("A"), _spec("B", "A"), _spec("C"))

    run, outcomes = await _execute(db_session, registry, provider)

    assert outcomes["A"].status == FAILED
    assert "A" in outcomes["A"].error or "LLM call failed" in outcomes["A"].error
    assert outcomes["C"].status == COMPLETED
    assert "B" not in outcomes
    executions = await _executions_by_type(db_session, run)
    assert {t: e.status for t, e in executions.items()} == {"A": FAILED, "B": BLOCKED, "C": COMPLETED}
    blocked_event = (
        await db_session.execute(select(Event).where(Event.event_type == "agent.blocked"))
    ).scalar_one()
    assert blocked_event.agent_execution_id == executions["B"].id
    assert blocked_event.payload["blocked_by"] == ["A"]


async def test_failure_mid_chain_blocks_the_rest_of_the_chain(db_session):
    provider = _ProbeProvider(fail_tasks={"task-B"})
    registry = _registry(_spec("A"), _spec("B", "A"), _spec("C", "B"))

    run, outcomes = await _execute(db_session, registry, provider)

    assert [(t, o.status) for t, o in outcomes.items()] == [("A", COMPLETED), ("B", FAILED)]
    executions = await _executions_by_type(db_session, run)
    assert executions["C"].status == BLOCKED


async def test_no_new_agent_starts_after_a_failure(db_session):
    provider = _ProbeProvider(fail_tasks={"task-A"})
    registry = _registry(_spec("A"), _spec("B"))

    run, outcomes = await _execute(db_session, registry, provider, max_concurrency=1)

    assert outcomes["A"].status == FAILED
    assert "B" not in outcomes
    assert [e for e in provider.order if e[1] == "task-B"] == []
    assert (await _executions_by_type(db_session, run))["B"].status == BLOCKED


async def test_all_agents_failing_blocks_nothing(db_session):
    provider = _ProbeProvider(barrier=2, fail_tasks={"task-A", "task-B"})

    run, outcomes = await _execute(db_session, _registry(_spec("A"), _spec("B")), provider)

    assert [o.status for o in outcomes.values()] == [FAILED, FAILED]
    assert {e.status for e in (await _executions_by_type(db_session, run)).values()} == {FAILED}


async def test_empty_registry_runs_nothing(db_session):
    _, outcomes = await _execute(db_session, {}, _ProbeProvider())

    assert outcomes == {}


async def test_unschedulable_agent_is_reported(db_session):
    registry = _registry(_spec("A", "MISSING"))

    with pytest.raises(RuntimeError, match="A"):
        await _execute(db_session, registry, _ProbeProvider())


async def test_every_agent_gets_its_own_session_and_commits_it(db_session):
    base = _factory(db_session)
    issued = []

    def factory():
        session = base()
        issued.append(session)
        return session

    run, _ = await _execute(db_session, _registry(_spec("A"), _spec("B")), _ProbeProvider(), session_factory=factory)

    assert len(issued) == 2 and issued[0] is not issued[1]
    assert all(session is not db_session for session in issued)
    # Committed by the agents' own sessions, so visible from this independent session.
    executions = await _executions_by_type(db_session, run)
    assert {e.status for e in executions.values()} == {COMPLETED}


async def test_unexpected_error_cancels_other_agents_and_propagates(db_session, monkeypatch):
    original = scheduler_module.build_context_payload

    async def _failing_for_b(db, *, objective, spec, previous_results):
        if spec.agent_type == "B":
            raise RuntimeError("digital twin unreachable")
        return await original(db, objective=objective, spec=spec, previous_results=previous_results)

    monkeypatch.setattr(scheduler_module, "build_context_payload", _failing_for_b)
    provider = _ProbeProvider(hang_tasks={"task-A"})
    before = asyncio.all_tasks()

    with pytest.raises(RuntimeError, match="digital twin unreachable"):
        await _execute(db_session, _registry(_spec("A"), _spec("B")), provider)

    assert asyncio.all_tasks() - before == set()


async def test_cancelling_the_scheduler_cancels_running_agents(db_session):
    provider = _ProbeProvider(hang_tasks={"task-A"})
    run, iteration = await _make_run(db_session)
    before = asyncio.all_tasks()

    task = asyncio.create_task(run_agents(**_kwargs(db_session, run, iteration, _registry(_spec("A")), provider)))
    await asyncio.wait_for(provider.hanging.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert provider.cancelled == ["task-A"]
    assert asyncio.all_tasks() - before == set()
