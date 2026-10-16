import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.schemas import (
    CargoRecommendation, CrewRecommendation, EmissionsRecommendation, FinanceRecommendation, FleetRecommendation,
    MaintenanceRecommendation, MarketRecommendation, NetworkRecommendation, WeatherRecommendation,
)
from app.api.deps import get_bus, get_db, get_llm_provider
from app.api.runs import router as runs_router
from app.events.bus import EventBus
from app.llm.fake_provider import FakeLLMProvider
from app.seed.seed import run_seed
from fastapi import FastAPI

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
    def __init__(self, network_provider, fleet_provider, maintenance_provider=None, crew_provider=None,
                 cargo_provider=None, finance_provider=None, emissions_provider=None, weather_provider=None,
                 market_provider=None):
        self._network_provider = network_provider
        self._fleet_provider = fleet_provider
        self._maintenance_provider = maintenance_provider or FakeLLMProvider(canned_response=MAINTENANCE_CANNED)
        self._crew_provider = crew_provider or FakeLLMProvider(canned_response=CREW_CANNED)
        self._cargo_provider = cargo_provider or FakeLLMProvider(canned_response=CARGO_CANNED)
        self._finance_provider = finance_provider or FakeLLMProvider(canned_response=FINANCE_CANNED)
        self._emissions_provider = emissions_provider or FakeLLMProvider(canned_response=EMISSIONS_CANNED)
        self._weather_provider = weather_provider or FakeLLMProvider(canned_response=WEATHER_CANNED)
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
        elif output_schema is MarketRecommendation:
            provider = self._market_provider
        else:
            provider = self._fleet_provider
        return await provider.complete(
            system_instructions=system_instructions, context=context, task=task,
            available_tools=available_tools, output_schema=output_schema,
        )


def _build_app(db_session, llm_provider=None):
    app = FastAPI()
    app.include_router(runs_router)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_bus] = lambda: EventBus()
    app.dependency_overrides[get_llm_provider] = lambda: llm_provider or _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )
    return app


async def test_post_runs_creates_and_returns_completed_run(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/runs", json={"objective": "Improve profitability"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["objective"] == "Improve profitability"


async def test_get_runs_lists_created_runs(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/runs", json={"objective": "Improve profitability"})
        response = await client.get("/api/runs")

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_get_run_detail_includes_agent_executions_and_decision(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        response = await client.get(f"/api/runs/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["agent_executions"]) == 9
    assert body["decision"]["summary"] == "Increase BOM-DEL frequency"
    # Each agent's structured output travels with the run, so the UI can show what every agent
    # recommended alongside the combined decision.
    by_type = {e["agent_type"]: e for e in body["agent_executions"]}
    assert by_type["NETWORK"]["recommendation"]["action"] == "INCREASE_FREQUENCY"
    assert by_type["NETWORK"]["recommendation"]["expected_revenue_impact"] == 300000.0
    assert by_type["FLEET"]["recommendation"]["aircraft_tail_number"] == "VT-AER1"
    assert by_type["MAINTENANCE"]["recommendation"]["grounded_aircraft"] == ["VT-AER3"]
    assert by_type["CREW"]["recommendation"]["assigned_crew"] == ["CR-001", "CR-003"]
    assert by_type["CARGO"]["recommendation"]["cargo_stance"] == "SUPPORTS"
    assert by_type["FINANCE"]["recommendation"]["financial_risk"] == "LOW"
    assert by_type["EMISSIONS"]["recommendation"]["emissions_stance"] == "SUPPORTS"


async def test_get_run_detail_missing_run_returns_404(db_session):
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/runs/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_get_run_graph_reflects_nodes_and_edges(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        response = await client.get(f"/api/runs/{created['id']}/graph")

    assert response.status_code == 200
    graph = response.json()
    node_types = [n["type"] for n in graph["nodes"]]
    assert "ORCHESTRATOR" in node_types
    assert "NETWORK_AGENT" in node_types
    assert "FLEET_AGENT" in node_types
    assert "DECISION_ENGINE" in node_types
    assert "FINAL_DECISION" in node_types
    # Agent nodes follow execution order (NETWORK runs before FLEET), not arbitrary row order.
    assert node_types.index("NETWORK_AGENT") < node_types.index("FLEET_AGENT")


async def test_post_runs_pipeline_failure_returns_200_with_failed_status(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(should_fail=True), FakeLLMProvider(canned_response=FLEET_CANNED)
    )
    app = _build_app(db_session, llm_provider=provider)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/runs", json={"objective": "Improve profitability"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED"


async def test_get_run_graph_shows_blocked_decision_engine_on_failed_run(db_session):
    await run_seed(db_session)
    provider = _DispatchingProvider(
        FakeLLMProvider(should_fail=True), FakeLLMProvider(canned_response=FLEET_CANNED)
    )
    app = _build_app(db_session, llm_provider=provider)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        response = await client.get(f"/api/runs/{created['id']}/graph")

    assert response.status_code == 200
    nodes_by_type = {n["type"]: n for n in response.json()["nodes"]}
    assert nodes_by_type["DECISION_ENGINE"]["status"] == "BLOCKED"
    assert "FINAL_DECISION" not in nodes_by_type


async def test_get_run_graph_shows_failed_context_engine_when_run_fails_before_any_agent(db_session, monkeypatch):
    await run_seed(db_session)

    async def _broken_build_context_payload(*args, **kwargs):
        raise RuntimeError("digital twin unreachable")

    import app.orchestrator.scheduler as scheduler_module
    monkeypatch.setattr(scheduler_module, "build_context_payload", _broken_build_context_payload)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        response = await client.get(f"/api/runs/{created['id']}/graph")

    assert created["status"] == "FAILED"
    nodes_by_type = {n["type"]: n for n in response.json()["nodes"]}
    assert nodes_by_type["CONTEXT_ENGINE"]["status"] == "FAILED"
    assert "NETWORK_AGENT" not in nodes_by_type


async def test_post_runs_rejects_empty_objective(db_session):
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/runs", json={"objective": ""})

    assert response.status_code == 422


async def test_post_runs_rejects_whitespace_only_objective(db_session):
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/runs", json={"objective": "   \n "})

    assert response.status_code == 422


async def test_post_runs_strips_surrounding_whitespace_from_objective(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/runs", json={"objective": "  Improve profitability\n"})

    assert response.status_code == 200
    assert response.json()["objective"] == "Improve profitability"


async def test_post_runs_with_real_llm_provider_dependency_and_no_api_key_fails_gracefully(
    db_session, monkeypatch
):
    """End-to-end: exercise the REAL get_llm_provider dependency (not overridden with a
    fake), with no OPENAI_API_KEY configured — reproduces the exact production scenario
    of a freshly deployed instance with no key set yet. Must return 200 with a FAILED
    run and full observability rows, not an unhandled 500 with nothing recorded."""
    monkeypatch.delenv("AEROTWIN_OPENAI_API_KEY", raising=False)
    from app.config import get_settings
    get_settings.cache_clear()

    await run_seed(db_session)
    app = FastAPI()
    app.include_router(runs_router)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_bus] = lambda: EventBus()
    # get_llm_provider is intentionally NOT overridden here.

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/runs", json={"objective": "Improve profitability"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED"

    get_settings.cache_clear()


async def test_post_run_prompt_adds_an_iteration_to_the_same_run(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        second = (
            await client.post(f"/api/runs/{created['id']}/prompts", json={"objective": "Now protect load factor"})
        ).json()
        detail = (await client.get(f"/api/runs/{created['id']}")).json()

    assert second["id"] == created["id"]  # the same run, reopened and completed again
    assert second["status"] == "COMPLETED"
    assert [i["sequence"] for i in detail["iterations"]] == [1, 2]
    assert [i["objective"] for i in detail["iterations"]] == ["Improve profitability", "Now protect load factor"]
    assert all(len(i["agent_executions"]) == 9 for i in detail["iterations"])
    assert all(i["decision"] is not None for i in detail["iterations"])
    # The flat lists still span the whole run.
    assert len(detail["agent_executions"]) == 18


async def test_post_run_prompt_missing_run_returns_404(db_session):
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/runs/{uuid.uuid4()}/prompts", json={"objective": "More"})

    assert response.status_code == 404


async def test_post_run_prompt_rejects_a_blank_objective(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        response = await client.post(f"/api/runs/{created['id']}/prompts", json={"objective": "   "})

    assert response.status_code == 422


async def test_get_run_graph_has_one_pipeline_group_per_iteration(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        await client.post(f"/api/runs/{created['id']}/prompts", json={"objective": "Now protect load factor"})
        graph = (await client.get(f"/api/runs/{created['id']}/graph")).json()

    node_types = [n["type"] for n in graph["nodes"]]
    assert node_types.count("CONTEXT_ENGINE") == 2
    assert node_types.count("FINAL_DECISION") == 2
    assert node_types.count("NETWORK_AGENT") == 2
    # Iterations chain: the first iteration's decision leads into the second's context.
    assert {"source": "final_decision-1", "target": "context_engine-2"} in graph["edges"]


async def test_get_run_knowledge_graph_shows_what_each_agent_knew(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        response = await client.get(f"/api/runs/{created['id']}/knowledge-graph")

    assert response.status_code == 200
    graph = response.json()
    types = {n["type"] for n in graph["nodes"]}
    assert {"AGENT", "ROUTE", "AIRCRAFT", "CONSTRAINT", "DECISION"} <= types
    labels = {n["label"] for n in graph["nodes"]}
    assert "NETWORK AGENT" in labels and "FLEET AGENT" in labels
    assert "BOM-DEL" in labels  # a seeded route the network agent read
    assert "VT-AER1" in labels  # the aircraft the fleet agent picked
    edge_labels = {e["label"] for e in graph["edges"]}
    assert {"knows", "respects", "informs", "feeds"} <= edge_labels


async def test_get_run_knowledge_graph_missing_run_returns_404(db_session):
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/runs/{uuid.uuid4()}/knowledge-graph")

    assert response.status_code == 404


# The endpoint functions, called directly rather than over HTTP. These assert the response models
# (not JSON), and unlike ASGI-transport requests their bodies are visible to coverage.
async def _provider():
    return _DispatchingProvider(
        FakeLLMProvider(canned_response=NETWORK_CANNED), FakeLLMProvider(canned_response=FLEET_CANNED)
    )


async def test_endpoint_functions_cover_a_runs_whole_lifecycle(db_session):
    from app.api.runs import (
        create_run, create_run_prompt, get_run, get_run_graph, get_run_knowledge_graph, list_runs,
    )
    from app.api.schemas import RunCreate

    await run_seed(db_session)
    bus = EventBus()
    provider = await _provider()

    run = await create_run(RunCreate(objective="Improve profitability"), db=db_session, bus=bus, llm_provider=provider)
    assert run.status == "COMPLETED"

    reopened = await create_run_prompt(
        run.id, RunCreate(objective="Now protect load factor"), db=db_session, bus=bus, llm_provider=provider
    )
    assert reopened.id == run.id

    assert [r.id for r in await list_runs(db=db_session)] == [run.id]

    detail = await get_run(run.id, db=db_session)
    assert [i.sequence for i in detail.iterations] == [1, 2]
    assert len(detail.agent_executions) == 18
    assert detail.iterations[1].decision is not None

    graph = await get_run_graph(run.id, db=db_session)
    assert [n["type"] for n in graph["nodes"]].count("FINAL_DECISION") == 2

    knowledge = await get_run_knowledge_graph(run.id, db=db_session)
    assert {n["type"] for n in knowledge["nodes"]} >= {"AGENT", "ROUTE", "AIRCRAFT", "DECISION"}


async def test_get_run_graph_falls_back_to_one_group_without_iterations(db_session):
    """Runs recorded before iterations existed have no RunIteration rows; their graph still renders."""
    from app.api.runs import get_run_graph
    from app.models.observability import (
        AgentExecution, AgentExecutionStatus, OrchestrationRun, OrchestrationRunStatus,
    )

    run = OrchestrationRun(objective="legacy", status=OrchestrationRunStatus.COMPLETED.value)
    db_session.add(run)
    await db_session.flush()
    db_session.add(AgentExecution(
        run_id=run.id, agent_type="NETWORK", status=AgentExecutionStatus.COMPLETED.value, task="t"
    ))
    await db_session.flush()

    graph = await get_run_graph(run.id, db=db_session)

    node_types = [n["type"] for n in graph["nodes"]]
    assert node_types.count("CONTEXT_ENGINE") == 1
    assert "NETWORK_AGENT" in node_types


async def test_get_run_messages_returns_agent_and_decision_engine_messages_in_order(db_session):
    await run_seed(db_session)
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        response = await client.get(f"/api/runs/{created['id']}/messages")

    assert response.status_code == 200
    messages = response.json()
    assert [(m["sender"], m["receiver"]) for m in messages] == [
        ("NETWORK_AGENT", "ORCHESTRATOR"), ("MAINTENANCE_AGENT", "ORCHESTRATOR"), ("FLEET_AGENT", "ORCHESTRATOR"),
        ("CREW_AGENT", "ORCHESTRATOR"), ("CARGO_AGENT", "ORCHESTRATOR"), ("WEATHER_AGENT", "ORCHESTRATOR"),
        ("FINANCE_AGENT", "ORCHESTRATOR"), ("EMISSIONS_AGENT", "ORCHESTRATOR"), ("MARKET_AGENT", "ORCHESTRATOR"),
        *[("ORCHESTRATOR", "DECISION_ENGINE")] * 9,
    ]
    assert all(m["run_id"] == created["id"] and m["context_id"] and m["payload"] for m in messages)
    assert {"id", "message_type", "created_at"} <= set(messages[0])


async def test_get_run_messages_is_empty_for_a_run_without_messages(db_session):
    await run_seed(db_session)
    failing = _DispatchingProvider(FakeLLMProvider(should_fail=True), FakeLLMProvider(canned_response=FLEET_CANNED))
    app = _build_app(db_session, llm_provider=failing)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/api/runs", json={"objective": "Improve profitability"})).json()
        response = await client.get(f"/api/runs/{created['id']}/messages")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_run_messages_404s_for_an_unknown_run(db_session):
    app = _build_app(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/runs/{uuid.uuid4()}/messages")

    assert response.status_code == 404
