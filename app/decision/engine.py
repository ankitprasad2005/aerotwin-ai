from app.agents.schemas import FleetRecommendation, NetworkRecommendation

_ACTION_WORDS = {
    "INCREASE_FREQUENCY": "Increase",
    "DECREASE_FREQUENCY": "Decrease",
    "MAINTAIN": "Maintain",
}


def _detect_conflicts(network: NetworkRecommendation, fleet: FleetRecommendation) -> list[str]:
    conflicts = []
    if network.action == "INCREASE_FREQUENCY" and fleet.aircraft_availability == "UNAVAILABLE":
        conflicts.append(
            f"Network agent recommends increasing frequency on {network.route}, but fleet "
            f"agent reports aircraft {fleet.aircraft_tail_number} is UNAVAILABLE."
        )
    if network.route != fleet.route:
        conflicts.append(
            f"Network agent analyzed route {network.route} but fleet agent analyzed route {fleet.route}."
        )
    if network.action == "INCREASE_FREQUENCY" and fleet.assignment_action == "NO_CHANGE":
        conflicts.append(
            f"Network agent recommends increasing frequency on {network.route}, but fleet "
            f"agent proposes NO_CHANGE to aircraft assignment."
        )
    if network.action in ("DECREASE_FREQUENCY", "MAINTAIN") and fleet.assignment_action == "ASSIGN_ADDITIONAL_AIRCRAFT":
        conflicts.append(
            f"Network agent recommends {network.action} on {network.route}, but fleet agent "
            f"proposes ASSIGN_ADDITIONAL_AIRCRAFT, which isn't warranted by that recommendation."
        )
    return conflicts


def reconcile(network: NetworkRecommendation, fleet: FleetRecommendation) -> dict:
    """Reconcile one NetworkRecommendation and one FleetRecommendation into a Decision-shaped dict.

    Checks: aircraft availability vs. a frequency increase, route agreement between the two
    recommendations, and fleet assignment action vs. network action consistency. Does NOT
    check every possible cross-recommendation contradiction — only these three.

    The caller (orchestrator) must add `run_id` and `agents_involved` before constructing
    a Decision ORM row, since reconcile() has no notion of the run or agent execution ids.
    """
    conflicts = _detect_conflicts(network, fleet)

    if conflicts:
        risk = "HIGH"
    elif network.confidence < 0.7 or fleet.confidence < 0.7:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    combined_cost_impact = network.expected_cost_impact + fleet.expected_cost_impact

    return {
        "summary": f"{_ACTION_WORDS[network.action]} {network.route} frequency",
        "expected_profit_impact": network.expected_revenue_impact - combined_cost_impact,
        "expected_revenue_impact": network.expected_revenue_impact,
        "expected_cost_impact": combined_cost_impact,
        "confidence": min(network.confidence, fleet.confidence),
        "risks": list(dict.fromkeys(network.risks + fleet.risks)),
        "constraints_checked": [
            "aircraft_availability_matches_action",
            "network_and_fleet_route_match",
            "fleet_assignment_matches_network_action",
        ],
        "validation_result": {
            "schema": "PASS",
            "constraints": "FAIL" if conflicts else "PASS",
            "conflicts": conflicts,
            "risk": risk,
        },
        "status": "RECOMMENDED",
    }
