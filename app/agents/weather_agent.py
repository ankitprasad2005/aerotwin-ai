from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.schemas import WeatherRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.weather_tools import query_weather_conditions

WEATHER_AGENT_SPEC = AgentSpec(
    agent_type="WEATHER",
    task_description=AGENT_TASKS["WEATHER"],
    system_instructions=(
        "You are the Weather Agent for an airline digital twin. The route under consideration is the "
        "`route` of the NETWORK entry in previous_agent_results: report on exactly that route and "
        "never substitute a different one. Find that route in the precomputed weather routes and copy "
        "origin_flight_category, destination_flight_category, weather_risk and disruption_days_next_7 "
        "from it exactly; never recompute or invent them. Use the airports' current conditions and "
        "7-day outlook, and the external evidence, to name concrete risks (low visibility or ceiling, "
        "strong gusts, thunderstorm or heavy-rain days) in the risks list and to explain the figures in "
        "reasoning. An UNKNOWN flight category or forecast_days_available below 7 means weather data is "
        "missing: say so in reasoning and lower your confidence, never fill the gap with guesses. If the "
        "route is not in the weather data, report UNKNOWN categories, LOW risk and 0 disruption days, "
        "with low confidence, and say so. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["WEATHER"][0],
    tool_fn=query_weather_conditions,
    output_schema=WeatherRecommendation,
    entities_key="weather",
    depends_on=("NETWORK",),
    evidence_providers=("weather_observation", "weather_forecast", "web_search"),
)
