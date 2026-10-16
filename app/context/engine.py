from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.spec import AgentSpec
from app.context.proposal import proposed_change_for
from app.evidence.gather import gather_evidence
from app.evidence.routing import routed_providers

AGENT_TASKS = {
    "NETWORK": "Identify profitable route frequency changes.",
    "FLEET": "Assess aircraft availability and assignment for proposed route changes.",
    "MAINTENANCE": "Assess aircraft airworthiness and upcoming maintenance.",
    "CREW": "Assess crew availability and assignment for proposed route changes.",
    "CARGO": "Assess belly-cargo demand and revenue for proposed route changes.",
    "FINANCE": "Assess the exposure of proposed route changes to jet fuel prices and the USD/INR exchange rate.",
    "EMISSIONS": "Assess the CO2 impact of the proposed route changes.",
    "WEATHER": "Assess weather risk at the origin and destination of proposed route changes.",
}

AGENT_TOOLS = {
    "NETWORK": ["query_route_profitability"],
    "FLEET": ["query_fleet_status"],
    "MAINTENANCE": ["query_maintenance_status"],
    "CREW": ["query_crew_status"],
    "CARGO": ["query_cargo_opportunities"],
    "FINANCE": ["query_financial_exposure"],
    "EMISSIONS": ["query_route_emissions"],
    "WEATHER": ["query_weather_conditions"],
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

    payload = {
        "objective": objective,
        "task": spec.task_description,
        "entities": {spec.entities_key: result[spec.entities_key]},
        "constraints": CONSTRAINTS,
        "previous_agent_results": previous,
        "evidence": evidence,
        "evidence_unavailable": evidence_unavailable,
        "evidence_routing": routed_providers(spec.agent_type, objective, spec.evidence_providers),
        "available_tools": [spec.tool_name],
        "metadata": {"agent_type": spec.agent_type},
    }
    if spec.agent_type == "NETWORK":
        proposal = await proposed_change_for(db, objective)
        if proposal is not None:
            payload["proposed_change"] = proposal
    return payload
