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


async def test_context_has_empty_evidence_keys_for_a_spec_without_providers(db_session):
    await run_seed(db_session)
    spec = AgentSpec(
        agent_type="X", task_description="t", system_instructions="s", tool_name="tool",
        tool_fn=NETWORK_AGENT_SPEC.tool_fn, output_schema=NetworkRecommendation, entities_key="routes",
    )

    payload = await build_context_payload(db_session, objective="x", spec=spec)

    assert payload["evidence"] == []
    assert payload["evidence_unavailable"] == []


async def test_context_includes_provider_evidence_and_unavailable_notes(db_session, monkeypatch):
    from app.evidence import catalog
    from app.evidence.base import EvidenceItem

    await run_seed(db_session)
    seen = []

    async def good(db, request):
        seen.append(request.route)
        return [EvidenceItem(id="fuel:x", source="eia_jet_fuel", kind="dataset", title="t", reliability=0.9, content="c")]

    async def bad(db, request):
        raise RuntimeError("down")

    monkeypatch.setattr(catalog, "EVIDENCE_PROVIDERS", {"good": good, "bad": bad})
    spec = AgentSpec(
        agent_type="X", task_description="t", system_instructions="s", tool_name="tool",
        tool_fn=NETWORK_AGENT_SPEC.tool_fn, output_schema=NetworkRecommendation, entities_key="routes",
        evidence_providers=("good", "bad"),
    )
    prior = [{"agent_type": "NETWORK", "route": "BOM-DEL"}]

    payload = await build_context_payload(db_session, objective="x", spec=spec, previous_results=prior)

    assert [e["id"] for e in payload["evidence"]] == ["fuel:x"]
    assert payload["evidence_unavailable"] == ["bad: RuntimeError: down"]
    assert seen == ["BOM-DEL"]
    assert payload["previous_agent_results"] == prior


async def test_context_records_which_providers_the_objective_routed_and_why(db_session, monkeypatch):
    from app.evidence import catalog
    from app.evidence.base import EvidenceItem

    await run_seed(db_session)

    async def provider(db, request):
        return [EvidenceItem(id="x:1", source="web", kind="web", title="t", reliability=0.4, content="c")]

    monkeypatch.setattr(catalog, "EVIDENCE_PROVIDERS", {"fuel_price": provider, "brent_price": provider})
    spec = AgentSpec(
        agent_type="FINANCE", task_description="t", system_instructions="s", tool_name="tool",
        tool_fn=NETWORK_AGENT_SPEC.tool_fn, output_schema=NetworkRecommendation, entities_key="routes",
        evidence_providers=("fuel_price",),
    )

    routed = await build_context_payload(db_session, objective="Hedge fuel exposure", spec=spec)
    plain = await build_context_payload(db_session, objective="Improve profitability", spec=spec)

    assert routed["evidence_routing"] == [{"provider": "brent_price", "topic": "fuel"}]
    assert plain["evidence_routing"] == []
