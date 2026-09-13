from app.agents.fleet_agent import FLEET_AGENT_SPEC
from app.agents.network_agent import NETWORK_AGENT_SPEC
from app.agents.schemas import FleetRecommendation, NetworkRecommendation
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.seed.seed import run_seed


def test_network_agent_spec_shape():
    assert NETWORK_AGENT_SPEC.agent_type == "NETWORK"
    assert NETWORK_AGENT_SPEC.tool_name == "query_route_profitability"
    assert NETWORK_AGENT_SPEC.output_schema is NetworkRecommendation


def test_fleet_agent_spec_shape():
    assert FLEET_AGENT_SPEC.agent_type == "FLEET"
    assert FLEET_AGENT_SPEC.tool_name == "query_fleet_status"
    assert FLEET_AGENT_SPEC.output_schema is FleetRecommendation


async def test_network_agent_spec_tool_fn_runs_against_seeded_db(db_session):
    await run_seed(db_session)
    result = await NETWORK_AGENT_SPEC.tool_fn(db_session)
    assert any(r["route"] == "BOM-DEL" for r in result["routes"])


async def test_fleet_agent_spec_tool_fn_runs_against_seeded_db(db_session):
    await run_seed(db_session)
    result = await FLEET_AGENT_SPEC.tool_fn(db_session)
    assert any(a["tail_number"] == "VT-AER1" for a in result["aircraft"])


def test_network_agent_spec_task_and_tool_match_context_engine_constants():
    assert NETWORK_AGENT_SPEC.task_description == AGENT_TASKS["NETWORK"]
    assert NETWORK_AGENT_SPEC.tool_name == AGENT_TOOLS["NETWORK"][0]


def test_fleet_agent_spec_task_and_tool_match_context_engine_constants():
    assert FLEET_AGENT_SPEC.task_description == AGENT_TASKS["FLEET"]
    assert FLEET_AGENT_SPEC.tool_name == AGENT_TOOLS["FLEET"][0]
