import pytest
from sqlalchemy import select

from app.agents.schemas import NetworkRecommendation
from app.agents.spec import AgentSpec
from app.events.bus import EventBus
from app.llm.fake_provider import FakeLLMProvider
from app.models.observability import (
    AgentExecution, AgentExecutionStatus, ContextSnapshot, Event, LLMExecution,
    OrchestrationRun, OrchestrationRunStatus,
)
from app.agents.runner import AgentRunError, block_agent, run_agent


async def _make_run(db_session):
    run = OrchestrationRun(objective="Improve profitability", status=OrchestrationRunStatus.RUNNING.value)
    db_session.add(run)
    await db_session.flush()
    return run


def _spec(tool_fn):
    return AgentSpec(
        agent_type="NETWORK",
        task_description="Identify profitable route frequency changes.",
        system_instructions="You are the network agent.",
        tool_name="query_route_profitability",
        tool_fn=tool_fn,
        output_schema=NetworkRecommendation,
    )


CANNED = {
    "route": "BOM-DEL",
    "action": "INCREASE_FREQUENCY",
    "expected_profit_impact": 125000.0,
    "expected_revenue_impact": 300000.0,
    "expected_cost_impact": 175000.0,
    "confidence": 0.82,
    "risks": ["fuel price volatility"],
    "reasoning": "Demand exceeds current capacity on this route.",
}


async def test_run_agent_completes_and_persists_full_chain(db_session):
    run = await _make_run(db_session)

    async def tool_fn(db):
        return {"routes": [{"route": "BOM-DEL", "current_frequency": 7}]}

    bus = EventBus()
    provider = FakeLLMProvider(canned_response=CANNED)

    execution, recommendation = await run_agent(
        db_session, bus=bus, run_id=run.id, spec=_spec(tool_fn),
        context_payload={"objective": run.objective, "entities": {}}, llm_provider=provider,
    )

    assert isinstance(recommendation, NetworkRecommendation)
    assert recommendation.route == "BOM-DEL"

    stored_execution = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.id == execution.id))
    ).scalar_one()
    assert stored_execution.status == AgentExecutionStatus.COMPLETED.value
    assert stored_execution.total_tokens == 180

    snapshot = (
        await db_session.execute(select(ContextSnapshot).where(ContextSnapshot.agent_execution_id == execution.id))
    ).scalar_one()
    assert snapshot.payload["objective"] == "Improve profitability"

    llm_exec = (
        await db_session.execute(select(LLMExecution).where(LLMExecution.agent_execution_id == execution.id))
    ).scalar_one()
    assert llm_exec.provider == "fake"


async def test_run_agent_llm_failure_marks_execution_failed_and_raises(db_session):
    run = await _make_run(db_session)

    async def tool_fn(db):
        return {"routes": []}

    bus = EventBus()
    provider = FakeLLMProvider(should_fail=True)

    with pytest.raises(AgentRunError):
        await run_agent(
            db_session, bus=bus, run_id=run.id, spec=_spec(tool_fn),
            context_payload={"objective": run.objective, "entities": {}}, llm_provider=provider,
        )

    stored_execution = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))
    ).scalar_one()
    assert stored_execution.status == AgentExecutionStatus.FAILED.value


async def test_run_agent_tool_failure_marks_execution_failed_and_raises(db_session):
    run = await _make_run(db_session)

    async def failing_tool(db):
        raise RuntimeError("digital twin unreachable")

    bus = EventBus()
    provider = FakeLLMProvider(canned_response=CANNED)

    with pytest.raises(AgentRunError):
        await run_agent(
            db_session, bus=bus, run_id=run.id, spec=_spec(failing_tool),
            context_payload={"objective": run.objective, "entities": {}}, llm_provider=provider,
        )

    stored_execution = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))
    ).scalar_one()
    assert stored_execution.status == AgentExecutionStatus.FAILED.value


async def test_run_agent_emits_full_event_sequence_on_success(db_session):
    run = await _make_run(db_session)

    async def tool_fn(db):
        return {"routes": [{"route": "BOM-DEL", "current_frequency": 7}]}

    bus = EventBus()
    queue = bus.subscribe()
    provider = FakeLLMProvider(canned_response=CANNED)

    await run_agent(
        db_session, bus=bus, run_id=run.id, spec=_spec(tool_fn),
        context_payload={"objective": run.objective, "entities": {}}, llm_provider=provider,
    )

    event_types = []
    while not queue.empty():
        event_types.append((await queue.get())["event_type"])

    assert event_types == [
        "agent.started", "context.created", "tool.called", "tool.completed",
        "llm.request", "llm.response", "agent.completed",
    ]


async def test_agent_run_error_carries_execution_id_and_agent_type(db_session):
    run = await _make_run(db_session)

    async def failing_tool(db):
        raise RuntimeError("digital twin unreachable")

    bus = EventBus()
    provider = FakeLLMProvider(canned_response=CANNED)

    try:
        await run_agent(
            db_session, bus=bus, run_id=run.id, spec=_spec(failing_tool),
            context_payload={"objective": run.objective, "entities": {}}, llm_provider=provider,
        )
        assert False, "expected AgentRunError"
    except AgentRunError as exc:
        assert exc.agent_type == "NETWORK"
        assert exc.agent_execution_id is not None


async def test_run_agent_llm_step_non_provider_exception_still_marks_failed(db_session):
    run = await _make_run(db_session)

    async def tool_fn(db):
        return {"routes": []}

    class _BrokenProvider:
        async def complete(self, **kwargs):
            raise IndexError("list index out of range")  # simulates e.g. empty choices[]

    bus = EventBus()

    with pytest.raises(AgentRunError):
        await run_agent(
            db_session, bus=bus, run_id=run.id, spec=_spec(tool_fn),
            context_payload={"objective": run.objective, "entities": {}}, llm_provider=_BrokenProvider(),
        )

    stored_execution = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))
    ).scalar_one()
    assert stored_execution.status == AgentExecutionStatus.FAILED.value


async def test_run_agent_malformed_llm_output_marks_execution_failed(db_session):
    run = await _make_run(db_session)

    async def tool_fn(db):
        return {"routes": []}

    bus = EventBus()
    provider = FakeLLMProvider(canned_response={"route": "BOM-DEL"})  # missing required fields

    with pytest.raises(AgentRunError):
        await run_agent(
            db_session, bus=bus, run_id=run.id, spec=_spec(tool_fn),
            context_payload={"objective": run.objective, "entities": {}}, llm_provider=provider,
        )

    stored_execution = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))
    ).scalar_one()
    assert stored_execution.status == AgentExecutionStatus.FAILED.value


async def test_block_agent_records_a_blocked_execution_and_event(db_session):
    run = await _make_run(db_session)
    spec = _spec(lambda db: None)

    execution = await block_agent(
        db_session, bus=EventBus(), run_id=run.id, iteration_id=None, spec=spec, blocked_by=["FLEET"]
    )

    assert execution.status == AgentExecutionStatus.BLOCKED.value
    assert execution.agent_type == "NETWORK"
    assert execution.task == spec.task_description
    event = (
        await db_session.execute(select(Event).where(Event.agent_execution_id == execution.id))
    ).scalar_one()
    assert event.event_type == "agent.blocked"
    assert event.severity == "WARN"
    assert event.payload == {"agent_type": "NETWORK", "blocked_by": ["FLEET"]}
