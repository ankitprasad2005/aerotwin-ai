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
    return conflicts


def reconcile(network: NetworkRecommendation, fleet: FleetRecommendation) -> dict:
    conflicts = _detect_conflicts(network, fleet)

    if conflicts:
        risk = "HIGH"
    elif network.confidence < 0.7 or fleet.confidence < 0.7:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "summary": f"{_ACTION_WORDS[network.action]} {network.route} frequency",
        "expected_profit_impact": network.expected_profit_impact,
        "expected_revenue_impact": network.expected_revenue_impact,
        "expected_cost_impact": network.expected_cost_impact + fleet.expected_cost_impact,
        "confidence": min(network.confidence, fleet.confidence),
        "risks": list(dict.fromkeys(network.risks + fleet.risks)),
        "constraints_checked": ["aircraft_availability_matches_action", "network_and_fleet_route_match"],
        "validation_result": {
            "schema": "PASS",
            "constraints": "FAIL" if conflicts else "PASS",
            "conflicts": conflicts,
            "risk": risk,
        },
        "status": "RECOMMENDED",
    }
