from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.schemas import CargoRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.digital_twin_tools import query_cargo_opportunities

CARGO_AGENT_SPEC = AgentSpec(
    agent_type="CARGO",
    task_description=AGENT_TASKS["CARGO"],
    system_instructions=(
        "You are the Cargo Agent for an airline digital twin. The route under consideration is the "
        "`route` of the NETWORK entry in previous_agent_results: report on exactly that route and "
        "never substitute a different one. Assess the belly-cargo effect of that entry's action. For "
        "INCREASE_FREQUENCY copy expected_revenue_impact and expected_cost_impact from the route's "
        "revenue_usd and cost_usd in impact_if_increase_by_one_weekly_flight; for DECREASE_FREQUENCY "
        "copy them from impact_if_decrease_by_one_weekly_flight (they are negative: cargo lost); for "
        "MAINTAIN both are 0. Never estimate your own figures. Set cargo_stance to SUPPORTS when the "
        "cargo profit change (revenue minus cost) is positive, OPPOSES when it is negative, and "
        "NEUTRAL when it is zero or the action is MAINTAIN. If the route has no cargo data, report "
        "NEUTRAL with zero impacts and say so in reasoning. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["CARGO"][0],
    tool_fn=query_cargo_opportunities,
    output_schema=CargoRecommendation,
    entities_key="cargo",
    depends_on=("NETWORK",),
    evidence_providers=("fx_rate", "fuel_price", "web_search", "world_bank_freight", "airport_throughput"),
)
