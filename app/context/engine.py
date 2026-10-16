from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.spec import AgentSpec
from app.evidence.gather import gather_evidence

AGENT_TASKS = {
    "NETWORK": "Identify profitable route frequency changes.",
    "FLEET": "Assess aircraft availability and assignment for proposed route changes.",
    "MAINTENANCE": "Assess aircraft airworthiness and upcoming maintenance.",
    "CREW": "Assess crew availability and assignment for proposed route changes.",
    "CARGO": "Assess belly-cargo demand and revenue for proposed route changes.",
    "EMISSIONS": "Assess the CO2 impact of the proposed route changes.",
}

AGENT_TOOLS = {
    "NETWORK": ["query_route_profitability"],
    "FLEET": ["query_fleet_status"],
    "MAINTENANCE": ["query_maintenance_status"],
    "CREW": ["query_crew_status"],
    "CARGO": ["query_cargo_opportunities"],
    "EMISSIONS": ["query_route_emissions"],
}

CONSTRAINTS = [
    "Do not recommend increasing frequency on a route with an unavailable aircraft.",
    "Do not recommend changes that reduce load factor below 50%.",
]


async def build_context_payload(
    db: AsyncSession,
    *,
    objective: str,
    spec: AgentSpec,
    previous_results: list[dict] | None = None,
) -> dict:
    """Assemble the structured context (objective/task/entities/constraints/
    previous_agent_results/available_tools/metadata) an agent's LLM call receives.

    The entities come from the spec's own tool, so adding an agent needs no change here.
    """
    result = await spec.tool_fn(db)
    if spec.entities_key not in result:
        raise ValueError(f"tool {spec.tool_name} returned no '{spec.entities_key}' entities")

    previous = previous_results or []
    evidence, evidence_unavailable = await gather_evidence(
        db, spec=spec, objective=objective, previous_results=previous
    )

    return {
        "objective": objective,
        "task": spec.task_description,
        "entities": {spec.entities_key: result[spec.entities_key]},
        "constraints": CONSTRAINTS,
        "previous_agent_results": previous,
        "evidence": evidence,
        "evidence_unavailable": evidence_unavailable,
        "available_tools": [spec.tool_name],
        "metadata": {"agent_type": spec.agent_type},
    }
