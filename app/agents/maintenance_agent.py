from app.agents.guidance import EVIDENCE_GUIDANCE
from app.agents.schemas import MaintenanceRecommendation
from app.agents.spec import AgentSpec
from app.context.engine import AGENT_TASKS, AGENT_TOOLS
from app.tools.digital_twin_tools import query_maintenance_status

MAINTENANCE_AGENT_SPEC = AgentSpec(
    agent_type="MAINTENANCE",
    task_description=AGENT_TASKS["MAINTENANCE"],
    system_instructions=(
        "You are the Maintenance Agent for an airline digital twin. Each aircraft in the data comes "
        "with its open maintenance items and a precomputed `airworthiness` of GROUNDED, DUE_SOON or "
        "SERVICEABLE. List every GROUNDED aircraft in grounded_aircraft and every DUE_SOON aircraft in "
        "at_risk_aircraft, copying tail numbers exactly and never inventing or reclassifying any. "
        "Give each aircraft that is not SERVICEABLE exactly one action: KEEP_GROUNDED for a grounded "
        "aircraft whose work is under way or overdue, SCHEDULE_CHECK for a DUE_SOON aircraft whose "
        "check should be booked, MONITOR for a DUE_SOON aircraft that can keep flying for now, or "
        "RELEASE only if its open items no longer restrict it. "
        "Respond only in the required structured format."
    )
    + " "
    + EVIDENCE_GUIDANCE,
    tool_name=AGENT_TOOLS["MAINTENANCE"][0],
    tool_fn=query_maintenance_status,
    output_schema=MaintenanceRecommendation,
    entities_key="maintenance",
    evidence_providers=("web_search",),
)
