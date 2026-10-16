from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.schemas import EmissionsRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.emissions_tools import query_route_emissions

EMISSIONS_AGENT_SPEC = AgentSpec(
    agent_type="EMISSIONS",
    task_description=AGENT_TASKS["EMISSIONS"],
    system_instructions=(
        "You are the Emissions Agent for an airline digital twin. The route under consideration is the "
        "`route` of the NETWORK entry in previous_agent_results: report on exactly that route and "
        "never substitute a different one. Assess the CO2 effect of that entry's action using the "
        "precomputed figures for that route. For INCREASE_FREQUENCY copy co2_change_tonnes_per_week, "
        "co2_per_passenger_kg_before, co2_per_passenger_kg_after and emissions_stance from "
        "impact_if_increase_by_one_weekly_flight; for DECREASE_FREQUENCY copy them from "
        "impact_if_decrease_by_one_weekly_flight; for MAINTAIN use 0 for co2_change_tonnes_per_week, "
        "copy co2_per_passenger_kg_current into both per-passenger fields, and use NEUTRAL. "
        "Never estimate your own figures. If the chosen impact is null (no load data or the change "
        "would remove every flight), report zeros, NEUTRAL, and say so in reasoning. In reasoning, "
        "name the methodology from the route's methodology_sources and mention that fuel per flight "
        "is a type-average A320 estimate, not this airline's measured burn. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["EMISSIONS"][0],
    tool_fn=query_route_emissions,
    output_schema=EmissionsRecommendation,
    entities_key="emissions",
    depends_on=("NETWORK",),
    evidence_providers=("web_search",),
)
