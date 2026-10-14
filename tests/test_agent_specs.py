from app.agents.crew_agent import CREW_AGENT_SPEC
from app.agents.fleet_agent import FLEET_AGENT_SPEC
from app.agents.maintenance_agent import MAINTENANCE_AGENT_SPEC
from app.agents.network_agent import NETWORK_AGENT_SPEC
from app.agents.schemas import CrewRecommendation, FleetRecommendation, MaintenanceRecommendation, NetworkRecommendation
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


def test_network_agent_has_no_dependencies_and_fleet_depends_on_network_and_maintenance():
    assert NETWORK_AGENT_SPEC.depends_on == ()
    assert FLEET_AGENT_SPEC.depends_on == ("NETWORK", "MAINTENANCE")


def test_entities_keys_match_tool_results():
    assert NETWORK_AGENT_SPEC.entities_key == "routes"
    assert FLEET_AGENT_SPEC.entities_key == "aircraft"


def test_maintenance_agent_spec_shape():
    assert MAINTENANCE_AGENT_SPEC.agent_type == "MAINTENANCE"
    assert MAINTENANCE_AGENT_SPEC.tool_name == "query_maintenance_status"
    assert MAINTENANCE_AGENT_SPEC.output_schema is MaintenanceRecommendation
    assert MAINTENANCE_AGENT_SPEC.entities_key == "maintenance"
    assert MAINTENANCE_AGENT_SPEC.depends_on == ()  # runs in parallel with the network agent


def test_maintenance_agent_spec_task_and_tool_match_context_engine_constants():
    assert MAINTENANCE_AGENT_SPEC.task_description == AGENT_TASKS["MAINTENANCE"]
    assert MAINTENANCE_AGENT_SPEC.tool_name == AGENT_TOOLS["MAINTENANCE"][0]


async def test_maintenance_agent_spec_tool_fn_runs_against_seeded_db(db_session):
    await run_seed(db_session)
    result = await MAINTENANCE_AGENT_SPEC.tool_fn(db_session)
    assert any(a["airworthiness"] == "GROUNDED" for a in result["maintenance"])


def test_maintenance_instructions_tell_the_model_to_copy_airworthiness_from_the_tool():
    text = MAINTENANCE_AGENT_SPEC.system_instructions
    assert "airworthiness" in text and "GROUNDED" in text and "DUE_SOON" in text


def test_fleet_instructions_forbid_assigning_grounded_aircraft():
    text = FLEET_AGENT_SPEC.system_instructions
    assert "grounded_aircraft" in text and "at_risk_aircraft" in text


def test_crew_agent_spec_shape():
    assert CREW_AGENT_SPEC.agent_type == "CREW"
    assert CREW_AGENT_SPEC.tool_name == "query_crew_status"
    assert CREW_AGENT_SPEC.output_schema is CrewRecommendation
    assert CREW_AGENT_SPEC.entities_key == "crew"
    assert CREW_AGENT_SPEC.depends_on == ("NETWORK",)  # needs the route; runs in parallel with fleet


def test_crew_agent_spec_task_and_tool_match_context_engine_constants():
    assert CREW_AGENT_SPEC.task_description == AGENT_TASKS["CREW"]
    assert CREW_AGENT_SPEC.tool_name == AGENT_TOOLS["CREW"][0]


async def test_crew_agent_spec_tool_fn_runs_against_seeded_db(db_session):
    await run_seed(db_session)
    result = await CREW_AGENT_SPEC.tool_fn(db_session)
    assert any(m["employee_code"] == "CR-001" for m in result["crew"])


def test_crew_instructions_cover_the_pairing_rule_and_the_network_route():
    text = CREW_AGENT_SPEC.system_instructions
    for phrase in ("captain", "first officer", "NETWORK", "REPOSITION_CREW", "INSUFFICIENT"):
        assert phrase in text
