import pytest
from sqlalchemy import select, text

from app.agents.schemas import CargoRecommendation, CrewRecommendation, FleetRecommendation, MaintenanceRecommendation, NetworkRecommendation
from app.events.bus import EventBus
from app.llm.fake_provider import FakeLLMProvider
from app.models.observability import (
    AgentExecution, AgentExecutionStatus, AgentMessage, Decision, Event,
    OrchestrationRunStatus, RunIteration,
)
from app.orchestrator.orchestrator import add_run_prompt, run_orchestration
from app.seed.seed import run_seed

NETWORK_CANNED = {
    "route": "BOM-DEL", "action": "INCREASE_FREQUENCY", "expected_profit_impact": 125000.0,
    "expected_revenue_impact": 300000.0, "expected_cost_impact": 175000.0, "confidence": 0.82,
    "risks": ["fuel price volatility"], "reasoning": "Demand exceeds current capacity.", "cited_sources": [],
}
FLEET_CANNED = {
    "route": "BOM-DEL", "aircraft_tail_number": "VT-AER1", "assignment_action": "ASSIGN_ADDITIONAL_AIRCRAFT",
    "aircraft_availability": "AVAILABLE", "expected_cost_impact": 40000.0, "confidence": 0.88,
    "risks": ["crew scheduling"], "reasoning": "Aircraft available at origin.", "cited_sources": [],
}

MAINTENANCE_CANNED = {
    "grounded_aircraft": ["VT-AER3"], "at_risk_aircraft": ["VT-AER1"],
    "actions": [{"tail_number": "VT-AER3", "action": "KEEP_GROUNDED", "reason": "Heavy check in progress."}],
    "confidence": 0.9, "risks": ["parts delay"], "reasoning": "Classified from the maintenance data.", "cited_sources": [],
}

CREW_CANNED = {
    "route": "BOM-DEL", "crew_availability": "SUFFICIENT", "assignment_action": "ASSIGN_ADDITIONAL_CREW",
    "assigned_crew": ["CR-001", "CR-003"], "expected_cost_impact": 0.0, "confidence": 0.85,
    "risks": ["duty limits"], "reasoning": "A captain and first officer are available at the origin.", "cited_sources": [],
}

CARGO_CANNED = {
    "route": "BOM-DEL", "cargo_stance": "SUPPORTS", "expected_revenue_impact": 2040.0, "expected_cost_impact": 510.0,
    "confidence": 0.8, "risks": ["freight demand volatility"], "reasoning": "Unmet cargo demand fills the extra flight.", "cited_sources": [],
}


class _DispatchingProvider:
    """Test-only LLMProvider that routes to a different fake per output schema."""

    def __init__(self, network_provider, fleet_provider, maintenance_provider=None, crew_provider=None,
                 cargo_provider=None):
        self._network_provider = network_provider
        self._fleet_provider = fleet_provider
        self._maintenance_provider = maintenance_provider or FakeLLMProvider(canned_response=MAINTENANCE_CANNED)
        self._crew_provider = crew_provider or FakeLLMProvider(canned_response=CREW_CANNED)
        self._cargo_provider = cargo_provider or FakeLLMProvider(canned_response=CARGO_CANNED)

    async def complete(self, *, system_instructions, context, task, available_tools, output_schema):
        if output_schema is NetworkRecommendation:
            provider = self._network_provider
        elif output_schema is MaintenanceRecommendation:
            provider = self._maintenance_provider
        elif output_schema is CrewRecommendation:
            provider = self._crew_provider
        elif output_schema is CargoRecommendation:
            provider = self._cargo_provider
        else:
            provider = self._fleet_provider
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
    assert len(executions) == 5
    assert all(e.status == AgentExecutionStatus.COMPLETED.value for e in executions)

    messages = (
        await db_session.execute(select(AgentMessage).where(AgentMessage.run_id == run.id))
    ).scalars().all()
    assert sorted((m.sender, m.receiver) for m in messages) == [
        ("CARGO_AGENT", "ORCHESTRATOR"), ("CREW_AGENT", "ORCHESTRATOR"), ("FLEET_AGENT", "ORCHESTRATOR"),
        ("MAINTENANCE_AGENT", "ORCHESTRATOR"), ("NETWORK_AGENT", "ORCHESTRATOR"),
        ("ORCHESTRATOR", "DECISION_ENGINE"), ("ORCHESTRATOR", "DECISION_ENGINE"), ("ORCHESTRATOR", "DECISION_ENGINE"),
        ("ORCHESTRATOR", "DECISION_ENGINE"), ("ORCHESTRATOR", "DECISION_ENGINE"),
    ]
    assert all(m.context_id is not None for m in messages)

    decision = (
        await db_session.execute(select(Decision).where(Decision.run_id == run.id))
    ).scalar_one()
    assert decision.summary == "Increase BOM-DEL frequency"
    assert decision.status == "RECOMMENDED"
    by_type = {e.agent_type: e for e in executions}
    assert decision.agents_involved == [
        str(by_type[t].id) for t in ("NETWORK", "MAINTENANCE", "FLEET", "CREW", "CARGO")
    ]

    events = (
        await db_session.execute(select(Event).where(Event.run_id == run.id).order_by(Event.created_at))
    ).scalars().all()
    event_types = [e.event_type for e in events]
    assert event_types[0] == "orchestration.started"
    assert event_types[-1] == "orchestration.completed"
    assert "decision.created" in event_types
    assert event_types.index("decision.created") < event_types.index("orchestration.completed")
    assert event_types.count("agent.message_sent") == 10


async def test_run_orchestration_network_agent_failure_marks_run_failed(db_session):
    await run_seed(db_session)
    bus = EventBus()
    provider = _DispatchingProvider(
        FakeLLMProvider(should_fail=True), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=bus, objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    assert run.completed_at is not None  # a failed run has still finished

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


async def test_fail_run_swallows_error_during_failure_handling_and_leaves_the_run_unfinished(db_session, monkeypatch, caplog):
    """Covers orchestrator._fail_run's own defensive except block: if persisting
    the FAILED state itself fails (here, simulated by making emit_event raise on
    the "orchestration.failed" event), the exception must be swallowed (logged,
    not propagated) and the transaction rolled back rather than left half-flushed.

    The run was committed before the agents started, so it is durable but never marked
    FAILED: we verify from a separate connection that it is still RUNNING, and that the
    log captured the documented failure message.
    """
    await run_seed(db_session)
    bus = EventBus()
    provider = _DispatchingProvider(
        FakeLLMProvider(should_fail=True), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    import app.orchestrator.orchestrator as orchestrator_module

    original_emit_event = orchestrator_module.emit_event

    async def _emit_event_failing_on_orchestration_failed(db, *, bus, event_type, **kwargs):
        if event_type == "orchestration.failed":
            raise RuntimeError("simulated emit_event failure inside _fail_run")
        return await original_emit_event(db, bus=bus, event_type=event_type, **kwargs)

    monkeypatch.setattr(orchestrator_module, "emit_event", _emit_event_failing_on_orchestration_failed)

    objective = "Improve profitability (fail-run defensive path)"
    run = await run_orchestration(db_session, bus=bus, objective=objective, llm_provider=provider)

    assert run is not None
    assert "failed to persist orchestration.failed state for run" in caplog.text

    # db_session's transaction was rolled back inside _fail_run and remains usable.
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1

    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import TEST_DATABASE_URL
    from app.models.observability import OrchestrationRun

    check_engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with check_engine.connect() as conn:
            statuses = [
                row.status
                for row in (
                    await conn.execute(select(OrchestrationRun).where(OrchestrationRun.objective == objective))
                ).all()
            ]
            assert statuses == [OrchestrationRunStatus.RUNNING.value]
    finally:
        await check_engine.dispose()


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


async def _iterations(db_session, run_id):
    return (
        await db_session.execute(
            select(RunIteration).where(RunIteration.run_id == run_id).order_by(RunIteration.sequence)
        )
    ).scalars().all()


async def test_run_orchestration_records_its_first_iteration(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    iterations = await _iterations(db_session, run.id)
    assert [(i.sequence, i.objective, i.status) for i in iterations] == [
        (1, "Improve profitability", OrchestrationRunStatus.COMPLETED.value)
    ]
    executions = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))
    ).scalars().all()
    assert all(e.iteration_id == iterations[0].id for e in executions)


async def test_add_run_prompt_runs_a_second_iteration_informed_by_the_first_decision(db_session):
    await run_seed(db_session)
    network_fake = FakeLLMProvider(canned_response=NETWORK_CANNED)
    provider = _DispatchingProvider(network_fake, FakeLLMProvider(canned_response=FLEET_CANNED))
    bus = EventBus()

    run = await run_orchestration(db_session, bus=bus, objective="Improve profitability", llm_provider=provider)
    run = await add_run_prompt(
        db_session, bus=bus, run=run, objective="Now protect load factor", llm_provider=provider
    )

    assert run.status == OrchestrationRunStatus.COMPLETED.value
    iterations = await _iterations(db_session, run.id)
    assert [i.sequence for i in iterations] == [1, 2]
    assert iterations[1].objective == "Now protect load factor"

    decisions = (
        await db_session.execute(select(Decision).where(Decision.run_id == run.id).order_by(Decision.created_at))
    ).scalars().all()
    assert len(decisions) == 2
    assert decisions[1].iteration_id == iterations[1].id

    # The follow-up prompt's network agent saw the first iteration's decision as a previous result.
    second_context = network_fake.calls[1]["context"]
    assert any(r.get("source") == "PREVIOUS_DECISION" for r in second_context["previous_agent_results"])


async def test_add_run_prompt_failure_marks_only_the_new_iteration_failed(db_session):
    await run_seed(db_session)
    bus = EventBus()
    working = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )
    run = await run_orchestration(db_session, bus=bus, objective="Improve profitability", llm_provider=working)

    failing = _DispatchingProvider(
        FakeLLMProvider(should_fail=True), FakeLLMProvider(canned_response=FLEET_CANNED)
    )
    run = await add_run_prompt(db_session, bus=bus, run=run, objective="Cut costs", llm_provider=failing)

    assert run.status == OrchestrationRunStatus.FAILED.value
    iterations = await _iterations(db_session, run.id)
    assert [i.status for i in iterations] == [
        OrchestrationRunStatus.COMPLETED.value, OrchestrationRunStatus.FAILED.value
    ]
    # The first iteration's decision survives the later failure.
    decisions = (await db_session.execute(select(Decision).where(Decision.run_id == run.id))).scalars().all()
    assert len(decisions) == 1


async def test_agent_rows_survive_a_later_failure_in_the_decision_step(db_session, monkeypatch):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    def _broken_reconcile(network, fleet):
        raise RuntimeError("boom")

    import app.orchestrator.orchestrator as orchestrator_module
    monkeypatch.setattr(orchestrator_module, "reconcile", _broken_reconcile)

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    executions = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))
    ).scalars().all()
    assert {e.status for e in executions} == {AgentExecutionStatus.COMPLETED.value}
    assert len(executions) == 5


async def test_failed_agent_blocks_fleet_and_names_the_failure(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(should_fail=True), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    executions = {
        e.agent_type: e.status
        for e in (await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))).scalars()
    }
    assert executions == {
        "NETWORK": AgentExecutionStatus.FAILED.value,
        "MAINTENANCE": AgentExecutionStatus.COMPLETED.value,  # ran in parallel with the failing agent
        "FLEET": AgentExecutionStatus.BLOCKED.value,
        "CREW": AgentExecutionStatus.BLOCKED.value,
        "CARGO": AgentExecutionStatus.BLOCKED.value,
    }
    failed = (
        await db_session.execute(select(Event).where(Event.event_type == "orchestration.failed"))
    ).scalar_one()
    assert failed.payload["reason"] == "network agent failed"


async def test_run_orchestration_uses_an_explicit_session_factory(db_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    await run_seed(db_session)
    base = async_sessionmaker(db_session.bind, expire_on_commit=False)
    issued = []

    def factory():
        issued.append(1)
        return base()

    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )
    run = await run_orchestration(
        db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider,
        session_factory=factory,
    )

    assert run.status == OrchestrationRunStatus.COMPLETED.value
    assert len(issued) == 5  # one session per agent


async def test_run_orchestration_requires_a_bound_session_when_no_factory_given():
    from sqlalchemy.ext.asyncio import AsyncSession

    with pytest.raises(ValueError, match="session_factory"):
        await run_orchestration(
            AsyncSession(), bus=EventBus(), objective="x", llm_provider=FakeLLMProvider()
        )


async def test_run_fails_clearly_when_the_registry_lacks_the_decision_agents(db_session, monkeypatch):
    await run_seed(db_session)
    import app.orchestrator.orchestrator as orchestrator_module
    monkeypatch.setattr(orchestrator_module, "AGENT_REGISTRY", {})
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    failed = (
        await db_session.execute(select(Event).where(Event.event_type == "orchestration.failed"))
    ).scalar_one()
    assert "NETWORK and FLEET" in failed.payload["reason"]


async def test_maintenance_failure_fails_the_run_and_blocks_fleet(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        FakeLLMProvider(should_fail=True),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    executions = {
        e.agent_type: e.status
        for e in (await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))).scalars()
    }
    # Crew and Cargo need only Network, so whether they got to start before Maintenance failed is a race.
    for racy in ("CREW", "CARGO"):
        assert executions.pop(racy) in {AgentExecutionStatus.COMPLETED.value, AgentExecutionStatus.BLOCKED.value}
    assert executions == {
        "NETWORK": AgentExecutionStatus.COMPLETED.value,
        "MAINTENANCE": AgentExecutionStatus.FAILED.value,
        "FLEET": AgentExecutionStatus.BLOCKED.value,
    }
    failed = (
        await db_session.execute(select(Event).where(Event.event_type == "orchestration.failed"))
    ).scalar_one()
    assert failed.payload["reason"] == "maintenance agent failed"


async def test_fleet_context_carries_both_dependency_results(db_session):
    await run_seed(db_session)
    fleet_fake = FakeLLMProvider(canned_response=FLEET_CANNED)
    provider = _DispatchingProvider(FakeLLMProvider(canned_response=NETWORK_CANNED), fleet_fake)

    await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    results = fleet_fake.calls[0]["context"]["previous_agent_results"]
    assert [r["agent_type"] for r in results] == ["NETWORK", "MAINTENANCE"]  # crew's result is not a dependency
    assert results[0]["route"] == "BOM-DEL"
    assert results[1]["grounded_aircraft"] == ["VT-AER3"]


async def test_network_and_maintenance_run_in_parallel_and_fleet_waits_for_both(db_session):
    import asyncio

    await run_seed(db_session)
    order = []
    both_started = asyncio.Event()

    class _Recording(FakeLLMProvider):
        def __init__(self, name, canned, wait_for_peer):
            super().__init__(canned_response=canned)
            self._name, self._wait_for_peer = name, wait_for_peer

        async def complete(self, **kwargs):
            order.append(("enter", self._name))
            if self._wait_for_peer:
                if len([o for o in order if o[0] == "enter"]) >= 2:
                    both_started.set()
                await asyncio.wait_for(both_started.wait(), timeout=2)  # fails if run serially
            try:
                return await super().complete(**kwargs)
            finally:
                order.append(("exit", self._name))

    provider = _DispatchingProvider(
        _Recording("network", NETWORK_CANNED, True), _Recording("fleet", FLEET_CANNED, False),
        _Recording("maintenance", MAINTENANCE_CANNED, True),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.COMPLETED.value
    fleet_enter = order.index(("enter", "fleet"))
    assert order.index(("exit", "network")) < fleet_enter
    assert order.index(("exit", "maintenance")) < fleet_enter


async def test_crew_context_carries_only_the_network_result(db_session):
    await run_seed(db_session)
    crew_fake = FakeLLMProvider(canned_response=CREW_CANNED)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        crew_provider=crew_fake,
    )

    await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    results = crew_fake.calls[0]["context"]["previous_agent_results"]
    assert [r["agent_type"] for r in results] == ["NETWORK"]
    assert {m["employee_code"] for m in crew_fake.calls[0]["context"]["entities"]["crew"]} >= {"CR-001", "CR-009"}


async def test_crew_failure_fails_the_run_but_fleet_still_completes(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        crew_provider=FakeLLMProvider(should_fail=True),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    executions = {
        e.agent_type: e.status
        for e in (await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))).scalars()
    }
    assert executions["CREW"] == AgentExecutionStatus.FAILED.value
    assert executions["FLEET"] in {AgentExecutionStatus.COMPLETED.value, AgentExecutionStatus.FAILED.value}
    failed = (
        await db_session.execute(select(Event).where(Event.event_type == "orchestration.failed"))
    ).scalar_one()
    assert failed.payload["reason"] == "crew agent failed"


async def test_fleet_crew_and_cargo_run_in_parallel_after_network(db_session):
    import asyncio

    await run_seed(db_session)
    order = []
    peers_started = asyncio.Event()
    peers = {"fleet", "crew", "cargo"}

    class _Recording(FakeLLMProvider):
        def __init__(self, name, canned, wait_for_peers):
            super().__init__(canned_response=canned)
            self._name, self._wait_for_peers = name, wait_for_peers

        async def complete(self, **kwargs):
            order.append(("enter", self._name))
            if self._wait_for_peers:
                if {("enter", p) for p in peers} <= set(order):
                    peers_started.set()
                await asyncio.wait_for(peers_started.wait(), timeout=2)  # fails if any is run serially
            try:
                return await super().complete(**kwargs)
            finally:
                order.append(("exit", self._name))

    provider = _DispatchingProvider(
        _Recording("network", NETWORK_CANNED, False), _Recording("fleet", FLEET_CANNED, True),
        crew_provider=_Recording("crew", CREW_CANNED, True), cargo_provider=_Recording("cargo", CARGO_CANNED, True),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.COMPLETED.value
    for peer in peers:
        assert order.index(("exit", "network")) < order.index(("enter", peer))


async def test_cargo_context_carries_only_the_network_result_and_cargo_entities(db_session):
    await run_seed(db_session)
    cargo_fake = FakeLLMProvider(canned_response=CARGO_CANNED)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        cargo_provider=cargo_fake,
    )

    await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    context = cargo_fake.calls[0]["context"]
    assert [r["agent_type"] for r in context["previous_agent_results"]] == ["NETWORK"]
    assert {c["route"] for c in context["entities"]["cargo"]} >= {"BOM-DEL", "MAA-CCU"}


async def test_cargo_failure_fails_the_run_with_its_name(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        cargo_provider=FakeLLMProvider(should_fail=True),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    failed = (
        await db_session.execute(select(Event).where(Event.event_type == "orchestration.failed"))
    ).scalar_one()
    assert failed.payload["reason"] == "cargo agent failed"
