from sqlalchemy import select

from app.agents.schemas import FleetRecommendation, NetworkRecommendation
from app.events.bus import EventBus
from app.llm.fake_provider import FakeLLMProvider
from app.models.observability import (
    AgentExecution, AgentExecutionStatus, AgentMessage, Decision, Event,
    OrchestrationRunStatus,
)
from app.orchestrator.orchestrator import run_orchestration
from app.seed.seed import run_seed

NETWORK_CANNED = {
    "route": "BOM-DEL", "action": "INCREASE_FREQUENCY", "expected_profit_impact": 125000.0,
    "expected_revenue_impact": 300000.0, "expected_cost_impact": 175000.0, "confidence": 0.82,
    "risks": ["fuel price volatility"], "reasoning": "Demand exceeds current capacity.",
}
FLEET_CANNED = {
    "route": "BOM-DEL", "aircraft_tail_number": "VT-AER1", "assignment_action": "ASSIGN_ADDITIONAL_AIRCRAFT",
    "aircraft_availability": "AVAILABLE", "expected_cost_impact": 40000.0, "confidence": 0.88,
    "risks": ["crew scheduling"], "reasoning": "Aircraft available at origin.",
}


class _DispatchingProvider:
    """Test-only LLMProvider that routes to a different fake per output schema."""

    def __init__(self, network_provider: FakeLLMProvider, fleet_provider: FakeLLMProvider):
        self._network_provider = network_provider
        self._fleet_provider = fleet_provider

    async def complete(self, *, system_instructions, context, task, available_tools, output_schema):
        provider = self._network_provider if output_schema is NetworkRecommendation else self._fleet_provider
        return await provider.complete(
            system_instructions=system_instructions, context=context, task=task,
            available_tools=available_tools, output_schema=output_schema,
        )


async def test_run_orchestration_happy_path_produces_decision(db_session):
    await run_seed(db_session)
    bus = EventBus()
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=bus, objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.COMPLETED.value

    executions = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))
    ).scalars().all()
    assert len(executions) == 2
    assert all(e.status == AgentExecutionStatus.COMPLETED.value for e in executions)

    messages = (
        await db_session.execute(select(AgentMessage).where(AgentMessage.run_id == run.id))
    ).scalars().all()
    assert {m.sender for m in messages} == {"NETWORK_AGENT", "FLEET_AGENT"}

    decision = (
        await db_session.execute(select(Decision).where(Decision.run_id == run.id))
    ).scalar_one()
    assert decision.summary == "Increase BOM-DEL frequency"
    assert decision.status == "RECOMMENDED"

    events = (
        await db_session.execute(select(Event).where(Event.run_id == run.id).order_by(Event.created_at))
    ).scalars().all()
    event_types = [e.event_type for e in events]
    assert event_types[0] == "orchestration.started"
    assert event_types[-1] == "orchestration.completed"
    assert "decision.created" in event_types
    assert event_types.index("decision.created") < event_types.index("orchestration.completed")


async def test_run_orchestration_network_agent_failure_marks_run_failed(db_session):
    await run_seed(db_session)
    bus = EventBus()
    provider = _DispatchingProvider(
        FakeLLMProvider(should_fail=True), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=bus, objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value

    decisions = (
        await db_session.execute(select(Decision).where(Decision.run_id == run.id))
    ).scalars().all()
    assert decisions == []

    events = (
        await db_session.execute(select(Event).where(Event.run_id == run.id).order_by(Event.created_at))
    ).scalars().all()
    assert events[-1].event_type == "orchestration.failed"


async def test_run_orchestration_fleet_agent_failure_marks_run_failed(db_session):
    await run_seed(db_session)
    bus = EventBus()
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(should_fail=True)
    )

    run = await run_orchestration(db_session, bus=bus, objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    decisions = (
        await db_session.execute(select(Decision).where(Decision.run_id == run.id))
    ).scalars().all()
    assert decisions == []


async def test_run_orchestration_unexpected_failure_after_both_agents_marks_run_failed(db_session, monkeypatch):
    await run_seed(db_session)
    bus = EventBus()
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    def _broken_reconcile(network, fleet):
        raise RuntimeError("simulated unexpected failure in reconcile")

    import app.orchestrator.orchestrator as orchestrator_module
    monkeypatch.setattr(orchestrator_module, "reconcile", _broken_reconcile)

    run = await run_orchestration(db_session, bus=bus, objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value

    decisions = (
        await db_session.execute(select(Decision).where(Decision.run_id == run.id))
    ).scalars().all()
    assert decisions == []

    events = (
        await db_session.execute(select(Event).where(Event.run_id == run.id).order_by(Event.created_at))
    ).scalars().all()
    assert events[-1].event_type == "orchestration.failed"
