from app.agents.schemas import NetworkRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.digital_twin_tools import query_route_profitability

NETWORK_AGENT_SPEC = AgentSpec(
    agent_type="NETWORK",
    task_description=AGENT_TASKS["NETWORK"],
    system_instructions=(
        "You are the Network Optimization Agent for an airline digital twin. "
        "Given route profitability, distance, demand, and historical load factor data, "
        "recommend exactly one route frequency change (increase, decrease, or maintain) "
        "that improves overall profitability while respecting operational constraints. "
        "Respond only in the required structured format."
    ),
    tool_name=AGENT_TOOLS["NETWORK"][0],
    tool_fn=query_route_profitability,
    output_schema=NetworkRecommendation,
)
