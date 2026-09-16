from app.api.knowledge_graph import build_knowledge_graph

NETWORK_CONTEXT = {
    "objective": "Improve profitability",
    "entities": {
        "routes": [
            {"route": "DEL-BOM", "current_frequency": 7, "demand": 17500, "weekly_profit_usd": 33957},
            {"route": "BLR-HYD", "current_frequency": 3, "demand": 4100, "weekly_profit_usd": 9855},
        ]
    },
    "constraints": ["Do not recommend increasing frequency on a route with an unavailable aircraft."],
    "previous_agent_results": [],
}
FLEET_CONTEXT = {
    "objective": "Improve profitability",
    "entities": {"aircraft": [{"tail_number": "VT-AER2", "status": "AVAILABLE", "location": "DEL"}]},
    "constraints": ["Do not recommend increasing frequency on a route with an unavailable aircraft."],
    "previous_agent_results": [{"agent_type": "NETWORK", "route": "DEL-BOM", "action": "INCREASE_FREQUENCY"}],
}
NETWORK_RECOMMENDATION = {"route": "DEL-BOM", "action": "INCREASE_FREQUENCY"}
FLEET_RECOMMENDATION = {
    "route": "DEL-BOM", "aircraft_tail_number": "VT-AER2", "assignment_action": "ASSIGN_ADDITIONAL_AIRCRAFT",
}


def _graph(**overrides):
    agents = [
        {
            "execution_id": "e1", "agent_type": "NETWORK", "status": "COMPLETED", "iteration": 1,
            "context": NETWORK_CONTEXT, "recommendation": NETWORK_RECOMMENDATION,
        },
        {
            "execution_id": "e2", "agent_type": "FLEET", "status": "COMPLETED", "iteration": 1,
            "context": FLEET_CONTEXT, "recommendation": FLEET_RECOMMENDATION,
        },
    ]
    decisions = [
        {
            "decision_id": "d1", "iteration": 1, "summary": "Increase DEL-BOM frequency",
            "risk": "LOW", "expected_profit_impact": 19557.0,
        }
    ]
    return build_knowledge_graph(**{"agents": agents, "decisions": decisions, **overrides})


def _nodes_by_id(graph):
    return {node["id"]: node for node in graph["nodes"]}


def _edge_labels(graph, source, target):
    return {e["label"] for e in graph["edges"] if e["source"] == source and e["target"] == target}


def test_agents_entities_constraints_and_decisions_all_become_nodes():
    graph = _graph()
    by_type = {}
    for node in graph["nodes"]:
        by_type.setdefault(node["type"], []).append(node)

    assert {"AGENT", "ROUTE", "AIRCRAFT", "CONSTRAINT", "DECISION"} <= set(by_type)
    assert len(by_type["AGENT"]) == 2
    assert {n["label"] for n in by_type["ROUTE"]} == {"DEL-BOM", "BLR-HYD"}
    assert by_type["DECISION"][0]["label"] == "Increase DEL-BOM frequency"


def test_entity_knowledge_is_shared_not_duplicated():
    """A route both agents know is one node with an edge from each — that's what connects the graph."""
    graph = _graph()

    assert len([n for n in graph["nodes"] if n["id"] == "route-DEL-BOM"]) == 1
    assert "knows" in _edge_labels(graph, "agent-e1", "route-DEL-BOM")
    assert "respects" in _edge_labels(graph, "agent-e2", "constraint-0")
    assert "knows" in _edge_labels(graph, "agent-e2", "aircraft-VT-AER2")


def test_recommendations_decisions_and_handoffs_are_edges():
    graph = _graph()

    assert "INCREASE_FREQUENCY" in _edge_labels(graph, "agent-e1", "route-DEL-BOM")
    assert "assigns" in _edge_labels(graph, "agent-e2", "aircraft-VT-AER2")
    # The fleet agent was informed by the network agent's recommendation.
    assert "informs" in _edge_labels(graph, "agent-e1", "agent-e2")
    assert "feeds" in _edge_labels(graph, "agent-e1", "decision-d1")
    assert "acts on" in _edge_labels(graph, "decision-d1", "route-DEL-BOM")


def test_route_detail_from_context_survives_a_later_recommendation_reference():
    graph = _graph()
    assert "weekly_profit_usd=33957" in _nodes_by_id(graph)["route-DEL-BOM"]["detail"]


def test_an_earlier_iterations_decision_informs_a_later_iterations_agent():
    graph = build_knowledge_graph(
        agents=[
            {
                "execution_id": "e1", "agent_type": "NETWORK", "status": "COMPLETED", "iteration": 1,
                "context": NETWORK_CONTEXT, "recommendation": NETWORK_RECOMMENDATION,
            },
            {
                "execution_id": "e3", "agent_type": "NETWORK", "status": "COMPLETED", "iteration": 2,
                "context": {**NETWORK_CONTEXT, "previous_agent_results": [{"source": "PREVIOUS_DECISION"}]},
                "recommendation": NETWORK_RECOMMENDATION,
            },
        ],
        decisions=[
            {"decision_id": "d1", "iteration": 1, "summary": "Increase DEL-BOM frequency", "risk": "LOW",
             "expected_profit_impact": 19557.0},
            {"decision_id": "d2", "iteration": 2, "summary": "Decrease MAA-CCU frequency", "risk": "LOW",
             "expected_profit_impact": 5604.0},
        ],
    )

    assert "informs" in _edge_labels(graph, "decision-d1", "agent-e3")
    # The second iteration's own decision doesn't inform its own agents.
    assert _edge_labels(graph, "decision-d2", "agent-e3") == set()


def test_an_agent_with_no_context_or_recommendation_still_appears():
    graph = build_knowledge_graph(
        agents=[{
            "execution_id": "e9", "agent_type": "NETWORK", "status": "FAILED", "iteration": 1,
            "context": {}, "recommendation": None,
        }],
        decisions=[],
    )

    assert _nodes_by_id(graph)["agent-e9"]["detail"] == "FAILED"
    assert graph["edges"] == []


def test_a_fleet_recommendation_naming_no_aircraft_adds_no_aircraft_node():
    graph = build_knowledge_graph(
        agents=[{
            "execution_id": "e2", "agent_type": "FLEET", "status": "COMPLETED", "iteration": 1,
            "context": {}, "recommendation": {"route": "DEL-BOM", "aircraft_tail_number": "NONE"},
        }],
        decisions=[],
    )

    assert [n for n in graph["nodes"] if n["type"] == "AIRCRAFT"] == []
