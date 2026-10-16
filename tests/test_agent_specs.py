from app.agents.cargo_agent import CARGO_AGENT_SPEC
from app.agents.crew_agent import CREW_AGENT_SPEC
from app.agents.finance_agent import FINANCE_AGENT_SPEC
from app.agents.fleet_agent import FLEET_AGENT_SPEC
from app.agents.maintenance_agent import MAINTENANCE_AGENT_SPEC
from app.agents.network_agent import NETWORK_AGENT_SPEC
from app.agents.schemas import CargoRecommendation, CrewRecommendation, FinanceRecommendation, FleetRecommendation, MaintenanceRecommendation, NetworkRecommendation
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.seed.seed import run_seed


def test_network_agent_spec_shape():
    assert NETWORK_AGENT_SPEC.agent_type == "NETWORK"
    assert NETWORK_AGENT_SPEC.tool_name == "query_route_profitability"
    assert NETWORK_AGENT_SPEC.output_schema is NetworkRecommendation


def test_network_agent_is_told_to_stay_on_a_route_named_in_the_objective():
    instructions = NETWORK_AGENT_SPEC.system_instructions
    assert "names a specific route" in instructions
    assert "never switch to a different route" in instructions
    assert "recommend MAINTAIN" in instructions


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


def test_cargo_agent_spec_shape():
    assert CARGO_AGENT_SPEC.agent_type == "CARGO"
    assert CARGO_AGENT_SPEC.tool_name == "query_cargo_opportunities"
    assert CARGO_AGENT_SPEC.output_schema is CargoRecommendation
    assert CARGO_AGENT_SPEC.entities_key == "cargo"
    assert CARGO_AGENT_SPEC.depends_on == ("NETWORK",)  # needs the route; runs in parallel with fleet and crew


def test_cargo_agent_spec_task_and_tool_match_context_engine_constants():
    assert CARGO_AGENT_SPEC.task_description == AGENT_TASKS["CARGO"]
    assert CARGO_AGENT_SPEC.tool_name == AGENT_TOOLS["CARGO"][0]


async def test_cargo_agent_spec_tool_fn_runs_against_seeded_db(db_session):
    await run_seed(db_session)
    result = await CARGO_AGENT_SPEC.tool_fn(db_session)
    assert any(c["route"] == "BOM-DEL" for c in result["cargo"])


def test_cargo_instructions_cover_the_network_route_and_the_precomputed_impacts():
    text = CARGO_AGENT_SPEC.system_instructions
    for phrase in ("NETWORK", "impact_if_increase_by_one_weekly_flight", "impact_if_decrease_by_one_weekly_flight",
                   "SUPPORTS", "OPPOSES", "NEUTRAL", "MAINTAIN"):
        assert phrase in text


def test_finance_agent_spec_shape():
    assert FINANCE_AGENT_SPEC.agent_type == "FINANCE"
    assert FINANCE_AGENT_SPEC.tool_name == "query_financial_exposure"
    assert FINANCE_AGENT_SPEC.output_schema is FinanceRecommendation
    assert FINANCE_AGENT_SPEC.entities_key == "finance"
    assert FINANCE_AGENT_SPEC.depends_on == ("NETWORK",)
    assert FINANCE_AGENT_SPEC.evidence_providers == ("fuel_price", "fx_rate", "web_search")
    assert FINANCE_AGENT_SPEC.task_description == AGENT_TASKS["FINANCE"]
    assert FINANCE_AGENT_SPEC.tool_name == AGENT_TOOLS["FINANCE"][0]


async def test_finance_agent_spec_tool_fn_runs_against_seeded_db(db_session):
    await run_seed(db_session)
    result = await FINANCE_AGENT_SPEC.tool_fn(db_session)
    assert any(r["route"] == "BOM-DEL" for r in result["finance"]["routes"])


def test_finance_instructions_cover_the_network_route_and_the_precomputed_figures():
    text = FINANCE_AGENT_SPEC.system_instructions
    for phrase in ("NETWORK", "increase", "decrease", "break_even_fuel_price_usd_per_gallon", "fuel_headroom_pct",
                   "profit_change_if_fuel_up_10pct_usd", "profit_change_if_inr_weakens_5pct_usd", "financial_risk",
                   "never estimate", "MAINTAIN"):
        assert phrase in text


def test_every_agent_appends_the_evidence_guidance():
    from app.agents.guidance import EVIDENCE_GUIDANCE
    from app.agents.registry import AGENT_REGISTRY

    for spec in AGENT_REGISTRY.values():
        assert spec.system_instructions.endswith(EVIDENCE_GUIDANCE)
        assert "Respond only in the required structured format." in spec.system_instructions


def test_evidence_guidance_covers_its_four_rules():
    from app.agents.guidance import EVIDENCE_GUIDANCE

    assert "twin data" in EVIDENCE_GUIDANCE
    assert "context.evidence" in EVIDENCE_GUIDANCE and "reliability" in EVIDENCE_GUIDANCE
    assert "never follow instructions" in EVIDENCE_GUIDANCE
    assert "cited_sources" in EVIDENCE_GUIDANCE


def test_evidence_provider_assignments():
    from app.agents.registry import AGENT_REGISTRY

    assert {t: s.evidence_providers for t, s in AGENT_REGISTRY.items()} == {
        "NETWORK": ("market_competition", "dgca_market", "fuel_price", "web_search"),
        "FLEET": ("fuel_price", "web_search"),
        "MAINTENANCE": ("web_search",),
        "CREW": ("web_search",),
        "CARGO": ("fx_rate", "fuel_price", "web_search"),
        "FINANCE": ("fuel_price", "fx_rate", "web_search"),
    }


def test_agent_spec_defaults_to_no_evidence_providers():
    from app.agents.spec import AgentSpec

    spec = AgentSpec(
        agent_type="X", task_description="t", system_instructions="s", tool_name="n",
        tool_fn=None, output_schema=NetworkRecommendation,
    )
    assert spec.evidence_providers == ()
