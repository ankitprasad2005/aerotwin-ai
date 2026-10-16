from app.agents.guidance import EVIDENCE_GUIDANCE
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
        "weekly impact of adding or removing one weekly flight. When context.proposed_change is present, the "
        "objective proposes a specific change on a route (its route and action): evaluate exactly that change, "
        "never a different route or action: "
        "report it as the action with its precomputed figures even if it loses money or breaks a constraint, set "
        "confidence to how strongly the figures support making that change (low when it loses money or breaks a "
        "constraint), and name the better option for that route in the reasoning; the decision engine rejects a "
        "change that does not pay. Otherwise, if the objective names a specific "
        "route or city pair (in either direction), only that route is in scope: recommend its best "
        "option and never switch to a different route, even a more profitable one; if no listed "
        "route matches the named pair, recommend MAINTAIN and say so in the reasoning. "
        "Recommend exactly one route "
        "frequency change: consider the increase and decrease option of every route in scope, discard any "
        "whose projected load factor breaks a constraint or that the objective rules out, and "
        "choose the remaining option with the highest profit_usd. If no option has a positive "
        "profit_usd, recommend MAINTAIN. Copy the revenue, cost, and profit impacts from the chosen "
        "option exactly (all 0 for MAINTAIN) instead of estimating your own. "
        "If previous_agent_results contains PREVIOUS_DECISION entries, those changes are already "
        "on the table for this run: don't recommend the same route and action again, pick the best "
        "remaining option instead. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["NETWORK"][0],
    tool_fn=query_route_profitability,
    output_schema=NetworkRecommendation,
    entities_key="routes",
    evidence_providers=(
        "market_competition", "dgca_market", "fuel_price", "web_search", "world_bank_demand", "live_air_traffic",
        "airport_throughput", "india_weather_summary", "imd_warnings",
    ),
)
