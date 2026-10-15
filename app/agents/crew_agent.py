from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.schemas import CrewRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.digital_twin_tools import query_crew_status

CREW_AGENT_SPEC = AgentSpec(
    agent_type="CREW",
    task_description=AGENT_TASKS["CREW"],
    system_instructions=(
        "You are the Crew Agent for an airline digital twin. The route under consideration is the "
        "`route` of the NETWORK entry in previous_agent_results: report on exactly that route and "
        "never substitute a different one. Each crew member comes with a precomputed `availability` "
        "of AVAILABLE, LIMITED or UNAVAILABLE; only AVAILABLE crew can be assigned. A frequency "
        "increase needs one AVAILABLE captain and one AVAILABLE first officer with the same "
        "qualified_aircraft_type: use ASSIGN_ADDITIONAL_CREW when such a pair is based at the route's "
        "origin, REPOSITION_CREW when the only pair is based elsewhere (then expected_cost_impact "
        "covers moving them, never the route's operating cost, which already includes crew), and "
        "crew_availability INSUFFICIENT with NO_CHANGE and no assigned_crew when no pair exists. "
        "List assigned_crew by employee code, copied exactly. A decrease or MAINTAIN needs no "
        "additional crew: use NO_CHANGE, SUFFICIENT, and no assigned_crew. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["CREW"][0],
    tool_fn=query_crew_status,
    output_schema=CrewRecommendation,
    entities_key="crew",
    depends_on=("NETWORK",),
    evidence_providers=("web_search",),
)
