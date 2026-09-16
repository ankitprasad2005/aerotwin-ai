"""Builds a run's knowledge graph: what each agent knew, and what it concluded.

Nodes are the agents plus the knowledge they worked from — the digital-twin entities in their
context, and the constraints they were given — and the decisions reconciled from them. Entities are
deduplicated across agents and iterations, so a route both agents looked at becomes one node with
edges from each: that sharing is what makes the graph connected rather than two separate trees.
"""

_ROUTE_DETAIL_KEYS = ("current_frequency", "demand", "historical_load_factor", "weekly_profit_usd")
_AIRCRAFT_DETAIL_KEYS = ("status", "location", "maintenance_status")


def _detail(entity: dict, keys: tuple[str, ...]) -> str:
    return " · ".join(f"{key}={entity[key]}" for key in keys if entity.get(key) is not None)


def build_knowledge_graph(*, agents: list[dict], decisions: list[dict]) -> dict:
    """Assemble {"nodes": [...], "edges": [...]} from per-agent knowledge and a run's decisions.

    `agents` entries carry execution_id, agent_type, status, iteration, context (the agent's
    context snapshot payload) and recommendation (its parsed output, or None).
    `decisions` entries carry decision_id, iteration, summary, risk and expected_profit_impact.
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_node(node_id: str, **fields) -> str:
        # First writer wins: an entity first seen in an agent's context keeps its richer detail
        # when a later recommendation references it again.
        nodes.setdefault(node_id, {"id": node_id, **fields})
        return node_id

    def add_edge(source: str, target: str, label: str) -> None:
        edge = {"source": source, "target": target, "label": label}
        if edge not in edges:
            edges.append(edge)

    decision_node_by_iteration: dict[object, str] = {}
    for decision in decisions:
        node_id = add_node(
            f"decision-{decision['decision_id']}",
            type="DECISION",
            label=decision.get("summary") or "DECISION",
            detail=_detail(decision, ("risk", "expected_profit_impact")),
            iteration=decision.get("iteration"),
            decision_id=decision["decision_id"],
        )
        decision_node_by_iteration[decision.get("iteration")] = node_id

    agent_node_by_iteration_and_type: dict[tuple, str] = {}
    for agent in agents:
        node_id = add_node(
            f"agent-{agent['execution_id']}",
            type="AGENT",
            label=f"{agent['agent_type']} AGENT",
            detail=agent.get("status") or "",
            iteration=agent.get("iteration"),
            agent_execution_id=agent["execution_id"],
        )
        agent_node_by_iteration_and_type[(agent.get("iteration"), agent["agent_type"])] = node_id

    for agent in agents:
        agent_node = f"agent-{agent['execution_id']}"
        context = agent.get("context") or {}
        entities = context.get("entities") or {}

        for route in entities.get("routes") or []:
            code = route.get("route")
            if code:
                add_edge(
                    agent_node,
                    add_node(f"route-{code}", type="ROUTE", label=code, detail=_detail(route, _ROUTE_DETAIL_KEYS)),
                    "knows",
                )
        for aircraft in entities.get("aircraft") or []:
            tail = aircraft.get("tail_number")
            if tail:
                add_edge(
                    agent_node,
                    add_node(
                        f"aircraft-{tail}", type="AIRCRAFT", label=tail,
                        detail=_detail(aircraft, _AIRCRAFT_DETAIL_KEYS),
                    ),
                    "knows",
                )
        for index, constraint in enumerate(context.get("constraints") or []):
            add_edge(
                agent_node,
                add_node(f"constraint-{index}", type="CONSTRAINT", label=f"CONSTRAINT {index + 1}", detail=str(constraint)),
                "respects",
            )

        for previous in context.get("previous_agent_results") or []:
            source_type = previous.get("agent_type")
            if source_type:
                source_node = agent_node_by_iteration_and_type.get((agent.get("iteration"), source_type))
                if source_node and source_node != agent_node:
                    add_edge(source_node, agent_node, "informs")
            elif previous.get("source") == "PREVIOUS_DECISION":
                for decision in decisions:
                    if (
                        decision.get("iteration") is not None
                        and agent.get("iteration") is not None
                        and decision["iteration"] < agent["iteration"]
                    ):
                        add_edge(f"decision-{decision['decision_id']}", agent_node, "informs")

        recommendation = agent.get("recommendation") or {}
        decision_node = decision_node_by_iteration.get(agent.get("iteration"))
        route_code = recommendation.get("route")
        if route_code:
            route_node = add_node(f"route-{route_code}", type="ROUTE", label=route_code, detail="")
            add_edge(agent_node, route_node, recommendation.get("action") or recommendation.get("assignment_action") or "recommends")
            if decision_node and agent["agent_type"] == "NETWORK":
                add_edge(decision_node, route_node, "acts on")
        tail = recommendation.get("aircraft_tail_number")
        if tail and tail.upper() != "NONE":
            add_edge(agent_node, add_node(f"aircraft-{tail}", type="AIRCRAFT", label=tail, detail=""), "assigns")
        if decision_node:
            add_edge(agent_node, decision_node, "feeds")

    return {"nodes": list(nodes.values()), "edges": edges}
