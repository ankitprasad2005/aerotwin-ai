from app.agents.schemas import FleetRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.digital_twin_tools import query_fleet_status

FLEET_AGENT_SPEC = AgentSpec(
    agent_type="FLEET",
    task_description=AGENT_TASKS["FLEET"],
    system_instructions=(
        "You are the Fleet Agent for an airline digital twin. Given current aircraft "
        "location, status, fuel level, flight hours, and maintenance status, recommend "
        "an aircraft assignment action for the route under consideration, and report "
        "the aircraft's current availability. Respond only in the required structured format."
    ),
    tool_name=AGENT_TOOLS["FLEET"][0],
    tool_fn=query_fleet_status,
    output_schema=FleetRecommendation,
)
