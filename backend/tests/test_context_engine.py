import pytest

from app.context.engine import build_context_payload
from app.seed.seed import run_seed


async def test_network_context_includes_routes_and_task(db_session):
    await run_seed(db_session)

    payload = await build_context_payload(db_session, objective="Improve profitability", agent_type="NETWORK")

    assert payload["objective"] == "Improve profitability"
    assert payload["task"] == "Identify profitable route frequency changes."
    assert any(r["route"] == "BOM-DEL" for r in payload["entities"]["routes"])
    assert "query_route_profitability" in payload["available_tools"]
    assert payload["previous_agent_results"] == []
    assert payload["metadata"]["agent_type"] == "NETWORK"


async def test_fleet_context_includes_aircraft(db_session):
    await run_seed(db_session)

    payload = await build_context_payload(db_session, objective="Improve profitability", agent_type="FLEET")

    assert any(a["tail_number"] == "VT-AER3" for a in payload["entities"]["aircraft"])
    assert "query_fleet_status" in payload["available_tools"]


async def test_context_carries_previous_agent_results(db_session):
    await run_seed(db_session)

    prior = [{"agent_type": "NETWORK", "route": "BOM-DEL", "action": "INCREASE_FREQUENCY"}]
    payload = await build_context_payload(
        db_session, objective="x", agent_type="FLEET", previous_results=prior
    )

    assert payload["previous_agent_results"] == prior


async def test_unknown_agent_type_raises_value_error(db_session):
    with pytest.raises(ValueError):
        await build_context_payload(db_session, objective="x", agent_type="CARGO")
