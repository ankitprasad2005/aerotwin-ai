import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.schemas import FleetRecommendation, NetworkRecommendation
from app.api.deps import get_bus, get_db, get_llm_provider
from app.api.runs import router as runs_router
from app.events.bus import EventBus
from app.llm.fake_provider import FakeLLMProvider
from app.seed.seed import run_seed
from fastapi import FastAPI

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
    def __init__(self, network_provider, fleet_provider):
        self._network_provider = network_provider
        self._fleet_provider = fleet_provider

    async def complete(self, *, system_instructions, context, task, available_tools, output_schema):
        provider = self._network_provider if output_schema is NetworkRecommendation else self._fleet_provider
        return await provider.complete(
            system_instructions=system_instructions, context=context, task=task,
            available_tools=available_tools, output_schema=output_schema,
        )


def _build_app(db_session):
    app = FastAPI()
    app.include_router(runs_router)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_bus] = lambda: EventBus()
    app.dependency_overrides[get_llm_provider] = lambda: _DispatchingProvider(
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
    assert len(body["agent_executions"]) == 2
    assert body["decision"]["summary"] == "Increase BOM-DEL frequency"


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
