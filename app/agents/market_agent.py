from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.schemas import MarketRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.market_tools import query_market_conditions

MARKET_AGENT_SPEC = AgentSpec(
    agent_type="MARKET",
    task_description=AGENT_TASKS["MARKET"],
    system_instructions=(
        "You are the Market Agent for an airline digital twin. The route under consideration is the "
        "`route` of the NETWORK entry in previous_agent_results: report on exactly that route and "
        "never substitute a different one. Find that route in the precomputed market routes and copy "
        "rival_airlines, competition_level and demand_outlook from it exactly; copy "
        "passenger_growth_pct (as national_passenger_growth_pct) and holidays_next_8_weeks from the "
        "national context; never recompute or invent them. Use the national context (passenger growth, "
        "GDP growth, upcoming holidays) and the external evidence to name concrete risks in the risks "
        "list (for example HIGH competition, a WEAK demand outlook, or an increase planned into a weak "
        "market) and to explain the figures in reasoning. A null figure or an entry in notes means data "
        "is missing: say so in reasoning and lower your confidence, never fill the gap with guesses. If "
        "the route is not in the market data, report 0 rivals, LOW competition, STABLE demand with low "
        "confidence, and say so. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["MARKET"][0],
    tool_fn=query_market_conditions,
    output_schema=MarketRecommendation,
    entities_key="market",
    depends_on=("NETWORK",),
    evidence_providers=("market_competition", "world_bank_demand", "india_holidays", "web_search"),
)
