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
        "Respond only in the required structured format."
    ),
    tool_name=AGENT_TOOLS["FLEET"][0],
    tool_fn=query_fleet_status,
    output_schema=FleetRecommendation,
)
