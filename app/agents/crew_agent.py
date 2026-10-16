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
        "`route` of the NETWORK entry in previous_agent_results, and the action is that entry's "
        "frequency change (increase or decrease by one weekly flight; MAINTAIN counts as a decrease "
        "for crew). Report on exactly that route and never substitute a different one. The tool has "
        "already decided feasibility: find the `route_assessments` entry for that route and copy "
        "its `if_increase_by_one_weekly_flight` (for an increase) or `if_decrease_by_one_weekly_flight` "
        "(for a decrease or MAINTAIN) into crew_availability, assignment_action, assigned_crew "
        "(employee codes, exactly as given) and expected_cost_impact. Do not re-judge feasibility "
        "from the per-member `crew` list and never override the assessment: it already applies the "
        "rules that only AVAILABLE crew can be assigned, a frequency increase needs one AVAILABLE "
        "captain and one AVAILABLE first officer qualified on the same aircraft type, "
        "ASSIGN_ADDITIONAL_CREW means such a pair is based at the route's origin, REPOSITION_CREW "
        "means a pair must be moved (its cost covers only the moving, never the route's operating "
        "cost, which already includes crew), and INSUFFICIENT with NO_CHANGE means no pair exists. "
        "Use the `crew` list only to explain the reasoning and risks (for example who is on leave or "
        "close to their duty limit). "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["CREW"][0],
    tool_fn=query_crew_status,
    output_schema=CrewRecommendation,
    entities_key="crew",
    depends_on=("NETWORK",),
    evidence_providers=("web_search", "india_weather_summary"),
)
