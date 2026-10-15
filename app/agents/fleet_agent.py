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
        "the `route` of the NETWORK entry in previous_agent_results: report on exactly that route "
        "and never substitute a different one. Given current aircraft location, status, fuel "
        "level, flight hours, and maintenance status, recommend an aircraft assignment action for "
        "it and report the chosen aircraft's current availability. A frequency increase needs an "
        "additional available aircraft, ideally one already at the route's origin; a decrease or "
        "MAINTAIN needs no additional aircraft (use NO_CHANGE). Your expected_cost_impact covers "
        "only the extra cost of making the aircraft available (such as repositioning it) — the "
        "route's operating cost is already counted by the network agent. "
        "The MAINTENANCE entry of previous_agent_results lists grounded_aircraft and at_risk_aircraft: "
        "never assign an aircraft in grounded_aircraft, prefer one not in at_risk_aircraft, and if every "
        "candidate is grounded report aircraft_availability UNAVAILABLE. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["FLEET"][0],
    tool_fn=query_fleet_status,
    output_schema=FleetRecommendation,
    entities_key="aircraft",
    depends_on=("NETWORK", "MAINTENANCE"),
    evidence_providers=("fuel_price", "web_search"),
)
