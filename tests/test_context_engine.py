import pytest

from app.agents.fleet_agent import FLEET_AGENT_SPEC
from app.agents.network_agent import NETWORK_AGENT_SPEC
from app.agents.schemas import NetworkRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import build_context_payload
from app.seed.seed import run_seed


async def test_network_context_includes_routes_and_task(db_session):
    await run_seed(db_session)

    payload = await build_context_payload(db_session, objective="Improve profitability", spec=NETWORK_AGENT_SPEC)

    assert payload["objective"] == "Improve profitability"
    assert payload["task"] == "Identify profitable route frequency changes."
    assert any(r["route"] == "BOM-DEL" for r in payload["entities"]["routes"])
    assert payload["available_tools"] == ["query_route_profitability"]
    assert payload["previous_agent_results"] == []
    assert payload["metadata"]["agent_type"] == "NETWORK"
    assert list(payload["entities"]) == ["routes"]


async def test_fleet_context_includes_aircraft(db_session):
    await run_seed(db_session)

    payload = await build_context_payload(db_session, objective="Improve profitability", spec=FLEET_AGENT_SPEC)

    assert any(a["tail_number"] == "VT-AER3" for a in payload["entities"]["aircraft"])
    assert payload["available_tools"] == ["query_fleet_status"]


async def test_context_carries_previous_agent_results(db_session):
    await run_seed(db_session)

    prior = [{"agent_type": "NETWORK", "route": "BOM-DEL", "action": "INCREASE_FREQUENCY"}]
    payload = await build_context_payload(
        db_session, objective="x", spec=FLEET_AGENT_SPEC, previous_results=prior
    )

    assert payload["previous_agent_results"] == prior


async def test_context_raises_when_tool_result_lacks_entities_key(db_session):
    async def tool(db):
        return {"something_else": []}

    spec = AgentSpec(
        agent_type="X", task_description="t", system_instructions="s", tool_name="tool",
        tool_fn=tool, output_schema=NetworkRecommendation, entities_key="routes",
    )
    with pytest.raises(ValueError, match="routes"):
        await build_context_payload(db_session, objective="x", spec=spec)
