from app.agents.schemas import NetworkRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.digital_twin_tools import query_route_profitability

NETWORK_AGENT_SPEC = AgentSpec(
    agent_type="NETWORK",
    task_description=AGENT_TASKS["NETWORK"],
    system_instructions=(
        "You are the Network Optimization Agent for an airline digital twin. "
        "Each route comes with its demand, load factor, fare, operating cost, and precomputed "
        "weekly impact of adding or removing one weekly flight. Recommend exactly one route "
        "frequency change: consider the increase and decrease option of every route, discard any "
        "whose projected load factor breaks a constraint or that the objective rules out, and "
        "choose the remaining option with the highest profit_usd. If no option has a positive "
        "profit_usd, recommend MAINTAIN. Copy the revenue, cost, and profit impacts from the chosen "
        "option exactly (all 0 for MAINTAIN) instead of estimating your own. "
        "Respond only in the required structured format."
    ),
    tool_name=AGENT_TOOLS["NETWORK"][0],
    tool_fn=query_route_profitability,
    output_schema=NetworkRecommendation,
)
