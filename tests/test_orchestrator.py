import pytest
from sqlalchemy import select, text

from app.agents.schemas import (
    CargoRecommendation, CrewRecommendation, EmissionsRecommendation, FinanceRecommendation, FleetRecommendation,
    MaintenanceRecommendation, MarketRecommendation, NetworkRecommendation, PricingRecommendation, WeatherRecommendation,
)
from app.events.bus import EventBus
from app.llm.fake_provider import FakeLLMProvider
from app.models.observability import (
    AgentExecution, AgentExecutionStatus, AgentMessage, Decision, Event,
    OrchestrationRunStatus, RunIteration,
)
from app.orchestrator.orchestrator import add_run_prompt, run_orchestration
from app.decision.weights import DEFAULT_WEIGHTS
from app.models.external import DecisionWeightProfile
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

FINANCE_CANNED = {
    "route": "BOM-DEL", "break_even_fuel_price_usd_per_gallon": 3.77, "fuel_headroom_pct": 71.43,
    "profit_change_if_fuel_up_10pct_usd": -280.0, "profit_change_if_inr_weakens_5pct_usd": -476.19,
    "financial_risk": "LOW", "confidence": 0.75, "risks": ["jet fuel price spike"],
    "reasoning": "Plenty of fuel headroom before the change stops paying.", "cited_sources": [],
}

EMISSIONS_CANNED = {
    "route": "BOM-DEL", "co2_change_tonnes_per_week": 18.086, "co2_per_passenger_kg_before": 124.05,
    "co2_per_passenger_kg_after": 111.64, "emissions_stance": "SUPPORTS", "confidence": 0.85,
    "risks": ["load factor may fall short of 90%"], "reasoning": "CO2 per passenger falls by 10%.", "cited_sources": [],
}

PRICING_CANNED = {
    "route": "BOM-DEL", "elasticity_used": -1.463, "fare_change_to_fill_added_seats_pct": None,
    "revenue_change_if_fare_minus_5pct_usd": -1200.0, "revenue_change_if_fare_plus_5pct_usd": 900.0,
    "pricing_stance": "SUPPORTS", "confidence": 0.8, "risks": ["elasticity is a literature average"],
    "reasoning": "Demand already fills the added seats.", "cited_sources": [],
}

WEATHER_CANNED = {
    "route": "BOM-DEL", "origin_flight_category": "VFR", "destination_flight_category": "MVFR", "weather_risk": "MODERATE",
    "disruption_days_next_7": 1, "confidence": 0.8, "risks": ["monsoon squalls"],
    "reasoning": "Delhi is MVFR and one forecast day is disrupted.", "cited_sources": [],
}


MARKET_CANNED = {
    "route": "BOM-DEL", "competition_level": "MODERATE", "rival_airlines": 3, "demand_outlook": "STABLE",
    "national_passenger_growth_pct": 3.2, "holidays_next_8_weeks": 1, "confidence": 0.8,
    "risks": ["fare competition"], "reasoning": "Three rivals fly the route and demand is stable.", "cited_sources": [],
}


class _DispatchingProvider:
    """Test-only LLMProvider that routes to a different fake per output schema."""

    def __init__(self, network_provider, fleet_provider, maintenance_provider=None, crew_provider=None,
                 cargo_provider=None, finance_provider=None, emissions_provider=None, weather_provider=None,
                 pricing_provider=None, market_provider=None):
        self._network_provider = network_provider
        self._fleet_provider = fleet_provider
        self._maintenance_provider = maintenance_provider or FakeLLMProvider(canned_response=MAINTENANCE_CANNED)
        self._crew_provider = crew_provider or FakeLLMProvider(canned_response=CREW_CANNED)
        self._cargo_provider = cargo_provider or FakeLLMProvider(canned_response=CARGO_CANNED)
        self._finance_provider = finance_provider or FakeLLMProvider(canned_response=FINANCE_CANNED)
        self._emissions_provider = emissions_provider or FakeLLMProvider(canned_response=EMISSIONS_CANNED)
        self._weather_provider = weather_provider or FakeLLMProvider(canned_response=WEATHER_CANNED)
        self._pricing_provider = pricing_provider or FakeLLMProvider(canned_response=PRICING_CANNED)
        self._market_provider = market_provider or FakeLLMProvider(canned_response=MARKET_CANNED)

    async def complete(self, *, system_instructions, context, task, available_tools, output_schema):
        if output_schema is NetworkRecommendation:
            provider = self._network_provider
        elif output_schema is MaintenanceRecommendation:
            provider = self._maintenance_provider
        elif output_schema is CrewRecommendation:
            provider = self._crew_provider
        elif output_schema is CargoRecommendation:
            provider = self._cargo_provider
        elif output_schema is FinanceRecommendation:
            provider = self._finance_provider
        elif output_schema is EmissionsRecommendation:
            provider = self._emissions_provider
        elif output_schema is WeatherRecommendation:
            provider = self._weather_provider
        elif output_schema is PricingRecommendation:
            provider = self._pricing_provider
        elif output_schema is MarketRecommendation:
            provider = self._market_provider
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
    assert len(executions) == 10
    assert all(e.status == AgentExecutionStatus.COMPLETED.value for e in executions)

    messages = (
        await db_session.execute(select(AgentMessage).where(AgentMessage.run_id == run.id))
    ).scalars().all()
    assert sorted((m.sender, m.receiver) for m in messages) == [
        ("CARGO_AGENT", "ORCHESTRATOR"), ("CREW_AGENT", "ORCHESTRATOR"), ("EMISSIONS_AGENT", "ORCHESTRATOR"),
        ("FINANCE_AGENT", "ORCHESTRATOR"), ("FLEET_AGENT", "ORCHESTRATOR"),
        ("MAINTENANCE_AGENT", "ORCHESTRATOR"), ("MARKET_AGENT", "ORCHESTRATOR"), ("NETWORK_AGENT", "ORCHESTRATOR"),
        *[("ORCHESTRATOR", "DECISION_ENGINE")] * 10,
        ("PRICING_AGENT", "ORCHESTRATOR"),
        ("WEATHER_AGENT", "ORCHESTRATOR"),
    ]
    assert all(m.context_id is not None for m in messages)

    decision = (
        await db_session.execute(select(Decision).where(Decision.run_id == run.id))
    ).scalar_one()
    assert decision.summary == "Increase BOM-DEL frequency"
    assert decision.status == "RECOMMENDED"
    by_type = {e.agent_type: e for e in executions}
    assert decision.agents_involved == [
        str(by_type[t].id) for t in ('NETWORK', 'MAINTENANCE', 'FLEET', 'CREW', 'CARGO', 'WEATHER', 'FINANCE', 'EMISSIONS', 'MARKET', 'PRICING')
    ]

    events = (
        await db_session.execute(select(Event).where(Event.run_id == run.id).order_by(Event.created_at))
    ).scalars().all()
    event_types = [e.event_type for e in events]
    assert event_types[0] == "orchestration.started"
    assert event_types[-1] == "orchestration.completed"
    assert "decision.created" in event_types
    assert event_types.index("decision.created") < event_types.index("orchestration.completed")
    assert event_types.count("agent.message_sent") == 20


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

    def _broken_reconcile(recommendations, **kwargs):
        raise RuntimeError("simulated unexpected failure in reconcile")

    import app.orchestrator.orchestrator as orchestrator_module
    monkeypatch.setattr(orchestrator_module, "reconcile_all", _broken_reconcile)

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

    def _broken_reconcile(recommendations, **kwargs):
        raise RuntimeError("boom")

    import app.orchestrator.orchestrator as orchestrator_module
    monkeypatch.setattr(orchestrator_module, "reconcile_all", _broken_reconcile)

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    executions = (
        await db_session.execute(select(AgentExecution).where(AgentExecution.run_id == run.id))
    ).scalars().all()
    assert {e.status for e in executions} == {AgentExecutionStatus.COMPLETED.value}
    assert len(executions) == 10


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
        "FINANCE": AgentExecutionStatus.BLOCKED.value,
        "EMISSIONS": AgentExecutionStatus.BLOCKED.value,
        "PRICING": AgentExecutionStatus.BLOCKED.value,
        "WEATHER": AgentExecutionStatus.BLOCKED.value,
        "MARKET": AgentExecutionStatus.BLOCKED.value,
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
    assert len(issued) == 10  # one session per agent


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
    # Crew, Cargo, Weather, Finance, Emissions, Market and Pricing need only Network, so whether they got to start before Maintenance failed is a race.
    for racy in ("CREW", "CARGO", "WEATHER", "FINANCE", "EMISSIONS", "MARKET", "PRICING"):
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


async def test_fleet_crew_cargo_and_finance_run_in_parallel_after_network(db_session):
    import asyncio

    await run_seed(db_session)
    order = []
    peers_started = asyncio.Event()
    peers = {"fleet", "crew", "cargo", "finance"}

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
        finance_provider=_Recording("finance", FINANCE_CANNED, True),
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


async def test_emissions_context_carries_only_the_network_result_and_emissions_entities(db_session):
    await run_seed(db_session)
    emissions_fake = FakeLLMProvider(canned_response=EMISSIONS_CANNED)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        emissions_provider=emissions_fake,
    )

    await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    context = emissions_fake.calls[0]["context"]
    assert [r["agent_type"] for r in context["previous_agent_results"]] == ["NETWORK"]
    assert {e["route"] for e in context["entities"]["emissions"]} >= {"BOM-DEL", "MAA-CCU"}
    assert all(e["methodology_sources"] for e in context["entities"]["emissions"])


async def test_emissions_failure_fails_the_run_with_its_name(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        emissions_provider=FakeLLMProvider(should_fail=True),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    failed = (
        await db_session.execute(select(Event).where(Event.event_type == "orchestration.failed"))
    ).scalar_one()
    assert failed.payload["reason"] == "emissions agent failed"


async def _the_decision(db_session, run):
    return (await db_session.execute(select(Decision).where(Decision.run_id == run.id))).scalar_one()


async def test_decision_carries_score_verdict_warnings_and_breakdown(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    vr = (await _the_decision(db_session, run)).validation_result
    assert vr["schema"] == "PASS" and vr["constraints"] == "PASS" and vr["conflicts"] == []
    assert vr["verdict"] == "RECOMMEND"
    # nothing cited -> data quality 0.5; the weather, finance, emissions, market and pricing confidences enter the weighted mean
    assert vr["score"] == pytest.approx(86.62, abs=0.01)
    assert vr["warnings"] and vr["risk"] == "MEDIUM"  # VT-AER1 is at risk in the canned maintenance output
    assert set(vr["score_breakdown"]) == {"profit", "confidence", "feasibility", "risk", "data_quality"}
    assert vr["score_breakdown"]["data_quality"]["value"] == 0.5


async def test_decision_uses_the_stored_weight_profile(db_session):
    await run_seed(db_session)
    weights = DEFAULT_WEIGHTS.model_dump()
    weights["thresholds"] = {"recommend": 99.9, "review": 98}
    db_session.add(DecisionWeightProfile(name="default", weights=weights))
    await db_session.commit()
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert (await _the_decision(db_session, run)).validation_result["verdict"] == "REJECT"


async def test_data_quality_is_the_mean_reliability_of_cited_evidence(db_session, monkeypatch):
    await run_seed(db_session)

    async def _fake_gather(db, *, spec, objective, previous_results):
        return [
            {"id": "fuel:eia:2026-10-10", "source": "eia_jet_fuel", "reliability": 0.9},
            {"id": f"web:{spec.agent_type}", "source": "web", "reliability": 0.4},
        ], []

    import app.context.engine as context_engine
    monkeypatch.setattr(context_engine, "gather_evidence", _fake_gather)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response={**NETWORK_CANNED, "cited_sources": ["fuel:eia:2026-10-10", "web:NETWORK"]}),
        FakeLLMProvider(canned_response={**FLEET_CANNED, "cited_sources": ["fuel:eia:2026-10-10", "web:ghost"]}),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    quality = (await _the_decision(db_session, run)).validation_result["score_breakdown"]["data_quality"]["value"]
    assert quality == pytest.approx((0.9 + 0.4) / 2)  # the ghost citation matches no evidence item


async def test_follow_up_iteration_decision_is_also_scored(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )
    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)
    await add_run_prompt(db_session, bus=EventBus(), run=run, objective="Again", llm_provider=provider)

    decisions = (await db_session.execute(select(Decision).where(Decision.run_id == run.id))).scalars().all()
    assert len(decisions) == 2
    assert all("verdict" in d.validation_result for d in decisions)


async def test_finance_context_carries_only_the_network_result_and_finance_entities(db_session):
    await run_seed(db_session)
    finance_fake = FakeLLMProvider(canned_response=FINANCE_CANNED)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        finance_provider=finance_fake,
    )

    await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    context = finance_fake.calls[0]["context"]
    assert [r["agent_type"] for r in context["previous_agent_results"]] == ["NETWORK"]
    assert {r["route"] for r in context["entities"]["finance"]["routes"]} >= {"BOM-DEL", "MAA-CCU"}
    assert set(context["entities"]["finance"]) == {"market", "notes", "price_basis", "routes", "airport_charges_info"}


async def test_finance_failure_fails_the_run_with_its_name(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        finance_provider=FakeLLMProvider(should_fail=True),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    failed = (
        await db_session.execute(select(Event).where(Event.event_type == "orchestration.failed"))
    ).scalar_one()
    assert failed.payload["reason"] == "finance agent failed"


@pytest.mark.parametrize("objective,verdict,conflicts", [
    ("Should we add a weekly flight on BOM-DEL?", "RECOMMEND", 0),      # the canned network answer is exactly that
    ("Should we cut a weekly flight on BOM-DEL?", "REJECT", 1),         # the canned answer increases instead
])
async def test_decision_checks_that_the_network_agent_answered_the_proposed_change(db_session, objective, verdict, conflicts):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective=objective, llm_provider=provider)

    decision = await _the_decision(db_session, run)
    assert "network_evaluates_proposed_change" in decision.constraints_checked
    assert decision.validation_result["verdict"] == verdict
    assert len(decision.validation_result["conflicts"]) == conflicts


async def test_pricing_context_carries_only_the_network_result_and_pricing_entities(db_session):
    await run_seed(db_session)
    pricing_fake = FakeLLMProvider(canned_response=PRICING_CANNED)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        pricing_provider=pricing_fake,
    )

    await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    context = pricing_fake.calls[0]["context"]
    assert [r["agent_type"] for r in context["previous_agent_results"]] == ["NETWORK"]
    assert {e["route"] for e in context["entities"]["pricing"]} >= {"BOM-DEL", "MAA-CCU"}
    assert all(e["elasticity_sources"] for e in context["entities"]["pricing"])


async def test_pricing_failure_fails_the_run_with_its_name(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED),
        pricing_provider=FakeLLMProvider(should_fail=True),
    )

    run = await run_orchestration(db_session, bus=EventBus(), objective="Improve profitability", llm_provider=provider)

    assert run.status == OrchestrationRunStatus.FAILED.value
    failed = (
        await db_session.execute(select(Event).where(Event.event_type == "orchestration.failed"))
    ).scalar_one()
    assert failed.payload["reason"] == "pricing agent failed"
