from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.spec import AgentSpec

AGENT_TASKS = {
    "NETWORK": "Identify profitable route frequency changes.",
    "FLEET": "Assess aircraft availability and assignment for proposed route changes.",
}

AGENT_TOOLS = {
    "NETWORK": ["query_route_profitability"],
    "FLEET": ["query_fleet_status"],
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

    return {
        "objective": objective,
        "task": spec.task_description,
        "entities": {spec.entities_key: result[spec.entities_key]},
        "constraints": CONSTRAINTS,
        "previous_agent_results": previous_results or [],
        "available_tools": [spec.tool_name],
        "metadata": {"agent_type": spec.agent_type},
    }
