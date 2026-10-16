from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.schemas import FleetRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.digital_twin_tools import query_fleet_status

FLEET_AGENT_SPEC = AgentSpec(
    agent_type="FLEET",
    task_description=AGENT_TASKS["FLEET"],
    system_instructions=(
        "You are the Fleet Agent for an airline digital twin. The route under consideration is "
        "the `route` of the NETWORK entry in previous_agent_results, and the action is that entry's "
        "frequency change (increase or decrease by one weekly flight; MAINTAIN counts as a decrease "
        "for the fleet). Report on exactly that route and never substitute a different one. The tool "
        "has already chosen the assignment: find the `route_assessments` entry for that route and "
        "copy its `if_increase_by_one_weekly_flight` (for an increase) or "
        "`if_decrease_by_one_weekly_flight` (for a decrease or MAINTAIN) into aircraft_tail_number, "
        "assignment_action, aircraft_availability and expected_cost_impact exactly, including "
        "NO_CHANGE with tail number NONE for a decrease or MAINTAIN, and UNAVAILABLE when no aircraft "
        "can be assigned. Never propose ASSIGN_ADDITIONAL_AIRCRAFT for a decrease or MAINTAIN. The "
        "assessment already excludes grounded aircraft (the same classification the MAINTENANCE "
        "entry of previous_agent_results reports in grounded_aircraft) and prefers aircraft at the "
        "origin and ones not in at_risk_aircraft; do not override it. expected_cost_impact covers only the "
        "repositioning of the aircraft — the route's operating cost is already counted by the "
        "network agent. Use the per-aircraft `aircraft` list and the MAINTENANCE entry only to "
        "explain the reasoning and risks. FAA airworthiness directives in the evidence are context for "
        "the risks and your confidence (many recent directives for a type means more maintenance "
        "exposure); they never change the assignment, and you must not invent any. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["FLEET"][0],
    tool_fn=query_fleet_status,
    output_schema=FleetRecommendation,
    entities_key="aircraft",
    depends_on=("NETWORK", "MAINTENANCE"),
    evidence_providers=("fuel_price", "web_search", "airworthiness_directives", "live_air_traffic"),
)
