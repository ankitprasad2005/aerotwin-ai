from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.schemas import PricingRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.pricing_tools import query_pricing_options

PRICING_AGENT_SPEC = AgentSpec(
    agent_type="PRICING",
    task_description=AGENT_TASKS["PRICING"],
    system_instructions=(
        "You are the Pricing Agent for an airline digital twin. The route under consideration is the "
        "`route` of the NETWORK entry in previous_agent_results: report on exactly that route and "
        "never substitute a different one. Assess the fare move that entry's action implies, using the "
        "precomputed figures for that route. For INCREASE_FREQUENCY copy "
        "fare_change_to_fill_added_seats_pct, revenue_change_if_fare_minus_5pct_usd, "
        "revenue_change_if_fare_plus_5pct_usd and pricing_stance from "
        "impact_if_increase_by_one_weekly_flight; for DECREASE_FREQUENCY copy them from "
        "impact_if_decrease_by_one_weekly_flight; for MAINTAIN use null for "
        "fare_change_to_fill_added_seats_pct, 0 for both revenue changes, and NEUTRAL. Always copy "
        "elasticity_used from the route. "
        "Never estimate your own figures. If the chosen impact is null (no demand data or the change "
        "would remove every flight), use null and zeros, NEUTRAL, and say so in reasoning. In reasoning, "
        "name the elasticity source from elasticity_sources and mention that it is a literature "
        "average for route-level fares, not this airline's measured price response. "
        "The `airport:` item of context.evidence gives the route's passenger charges (user development fee, "
        "paid by passengers on top of the fare): mention it when judging fare competitiveness and cite the item. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["PRICING"][0],
    tool_fn=query_pricing_options,
    output_schema=PricingRecommendation,
    entities_key="pricing",
    depends_on=("NETWORK",),
    evidence_providers=("market_competition", "fuel_price", "web_search", "airport_charges", "atf_india"),
)
