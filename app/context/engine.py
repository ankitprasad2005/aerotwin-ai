from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.digital_twin_tools import query_fleet_status, query_route_profitability

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
    agent_type: str,
    previous_results: list[dict] | None = None,
) -> dict:
    """Assemble the structured context (objective/task/entities/constraints/
    previous_agent_results/available_tools/metadata) an agent's LLM call receives."""
    if agent_type not in AGENT_TASKS:
        raise ValueError(f"unknown agent_type: {agent_type}")

    entities: dict = {}
    if agent_type == "NETWORK":
        entities["routes"] = (await query_route_profitability(db))["routes"]
    elif agent_type == "FLEET":
        entities["aircraft"] = (await query_fleet_status(db))["aircraft"]
    else:
        raise ValueError(f"unknown agent_type: {agent_type}")

    return {
        "objective": objective,
        "task": AGENT_TASKS[agent_type],
        "entities": entities,
        "constraints": CONSTRAINTS,
        "previous_agent_results": previous_results or [],
        "available_tools": AGENT_TOOLS[agent_type],
        "metadata": {"agent_type": agent_type},
    }
