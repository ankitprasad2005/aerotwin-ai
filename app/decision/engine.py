import math
from collections.abc import Iterable, Mapping

from pydantic import BaseModel

from app.decision.weights import DecisionWeights

_ACTION_WORDS = {
    "INCREASE_FREQUENCY": "Increase",
    "DECREASE_FREQUENCY": "Decrease",
    "MAINTAIN": "Maintain",
}

LOW_CONFIDENCE = 0.6
MEDIUM_RISK_CONFIDENCE = 0.7
BLOCKING_RISK_PENALTY = 0.5
WARNING_RISK_PENALTY = 0.15
NEUTRAL_DATA_QUALITY = 0.5

# A check is (name, conflict message or None when the check passed).
Check = tuple[str, str | None]


def sigmoid(x: float) -> float:
    """Logistic function that cannot overflow for huge |x| (and maps NaN to the neutral 0.5)."""
    if math.isnan(x):
        return 0.5
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))  # exp of a non-positive number never overflows
    e = math.exp(x)
    return e / (1.0 + e)


def evidence_reliability(
    recommendations: Mapping[str, BaseModel], evidence_by_agent: Mapping[str, Iterable[dict]]
) -> float | None:
    """Mean reliability of the distinct evidence items agents cited, or None when nothing valid was cited.

    A citation is valid only for an item in the citing agent's own evidence: an id it never received
    (even if another agent did) is an invented citation and does not count.
    """
    reliabilities: dict[str, float] = {}
    for agent_type, recommendation in recommendations.items():
        cited = set(getattr(recommendation, "cited_sources", None) or [])
        for item in evidence_by_agent.get(agent_type, ()):
            item_id, reliability = item.get("id"), item.get("reliability")
            if (
                item_id in cited
                and item_id not in reliabilities
                and isinstance(reliability, (int, float))
                and not isinstance(reliability, bool)
                and math.isfinite(reliability)
            ):
                reliabilities[item_id] = min(1.0, max(0.0, float(reliability)))
    if not reliabilities:
        return None
    return sum(reliabilities.values()) / len(reliabilities)


def _checks(recs: Mapping[str, BaseModel], profit: float) -> list[Check]:
    network, fleet = recs["NETWORK"], recs["FLEET"]
    increase = network.action == "INCREASE_FREQUENCY"
    checks: list[Check] = []

    unavailable = increase and fleet.aircraft_availability == "UNAVAILABLE"
    checks.append((
        "aircraft_availability_matches_action",
        f"Network agent recommends increasing frequency on {network.route}, but fleet "
        f"agent reports aircraft {fleet.aircraft_tail_number} is UNAVAILABLE." if unavailable else None,
    ))
    checks.append((
        "network_and_fleet_route_match",
        f"Network agent analyzed route {network.route} but fleet agent analyzed route {fleet.route}."
        if network.route != fleet.route else None,
    ))
    if increase and fleet.assignment_action == "NO_CHANGE":
        no_change = (
            f"Network agent recommends increasing frequency on {network.route}, but fleet "
            f"agent proposes NO_CHANGE to aircraft assignment."
        )
    elif network.action in ("DECREASE_FREQUENCY", "MAINTAIN") and fleet.assignment_action == "ASSIGN_ADDITIONAL_AIRCRAFT":
        no_change = (
            f"Network agent recommends {network.action} on {network.route}, but fleet agent "
            f"proposes ASSIGN_ADDITIONAL_AIRCRAFT, which isn't warranted by that recommendation."
        )
    else:
        no_change = None
    checks.append(("fleet_assignment_matches_network_action", no_change))
    checks.append((
        "change_has_positive_expected_profit",
        f"Network agent recommends {network.action} on {network.route}, but the expected weekly "
        f"profit impact including fleet costs is {profit:,.0f} USD, so the change "
        f"doesn't pay for itself." if network.action != "MAINTAIN" and profit <= 0 else None,
    ))

    maintenance = recs.get("MAINTENANCE")
    if maintenance is not None:
        grounded = increase and fleet.aircraft_tail_number in maintenance.grounded_aircraft
        checks.append((
            "aircraft_not_grounded",
            f"Fleet agent assigns aircraft {fleet.aircraft_tail_number} to increase frequency on "
            f"{network.route}, but the maintenance agent reports it is GROUNDED." if grounded else None,
        ))
    crew = recs.get("CREW")
    if crew is not None:
        checks.append((
            "crew_sufficient_for_increase",
            f"Network agent recommends increasing frequency on {network.route}, but the crew agent "
            f"reports crew availability is INSUFFICIENT." if increase and crew.crew_availability == "INSUFFICIENT" else None,
        ))
        checks.append((
            "crew_route_matches",
            f"Network agent analyzed route {network.route} but crew agent analyzed route {crew.route}."
            if crew.route != network.route else None,
        ))
    cargo = recs.get("CARGO")
    if cargo is not None:
        checks.append((
            "cargo_route_matches",
            f"Network agent analyzed route {network.route} but cargo agent analyzed route {cargo.route}."
            if cargo.route != network.route else None,
        ))
    finance = recs.get("FINANCE")
    if finance is not None:
        checks.append((
            "finance_route_matches",
            f"Network agent analyzed route {network.route} but finance agent analyzed route {finance.route}."
            if finance.route != network.route else None,
        ))
    emissions = recs.get("EMISSIONS")
    if emissions is not None:
        checks.append((
            "emissions_route_matches",
            f"Network agent analyzed route {network.route} but emissions agent analyzed route {emissions.route}."
            if emissions.route != network.route else None,
        ))
    weather = recs.get("WEATHER")
    if weather is not None:
        checks.append((
            "weather_route_matches",
            f"Network agent analyzed route {network.route} but weather agent analyzed route {weather.route}."
            if weather.route != network.route else None,
        ))
    market = recs.get("MARKET")
    if market is not None:
        checks.append((
            "market_route_matches",
            f"Network agent analyzed route {network.route} but market agent analyzed route {market.route}."
            if market.route != network.route else None,
        ))
    return checks


def _warnings(recs: Mapping[str, BaseModel]) -> list[str]:
    fleet = recs["FLEET"]
    warnings = []
    maintenance = recs.get("MAINTENANCE")
    if maintenance is not None and fleet.aircraft_tail_number in maintenance.at_risk_aircraft:
        warnings.append(
            f"Aircraft {fleet.aircraft_tail_number} is at risk of maintenance (due soon) but is assigned to {fleet.route}."
        )
    cargo = recs.get("CARGO")
    if cargo is not None and cargo.cargo_stance == "OPPOSES":
        warnings.append(f"Cargo agent opposes the change on {cargo.route}: it lowers weekly cargo profit.")
    finance = recs.get("FINANCE")
    if finance is not None and finance.financial_risk == "HIGH" and recs["NETWORK"].action != "MAINTAIN":
        warnings.append(
            f"Finance agent rates the change on {finance.route} as HIGH financial risk: it is highly sensitive "
            f"to the jet fuel price or already unprofitable."
        )
    emissions = recs.get("EMISSIONS")
    if emissions is not None and emissions.emissions_stance == "OPPOSES":
        warnings.append(
            f"Emissions agent opposes the change on {emissions.route}: it raises CO2 per passenger "
            f"({emissions.co2_per_passenger_kg_before:.1f} to {emissions.co2_per_passenger_kg_after:.1f} kg)."
        )
    crew = recs.get("CREW")
    if crew is not None and crew.assignment_action == "REPOSITION_CREW" and crew.expected_cost_impact > 0:
        warnings.append(
            f"Crew must be repositioned for {crew.route} at an extra cost of {crew.expected_cost_impact:,.0f} USD per week."
        )
    weather = recs.get("WEATHER")
    if weather is not None and weather.weather_risk == "HIGH" and recs["NETWORK"].action == "INCREASE_FREQUENCY":
        warnings.append(
            f"Weather risk is HIGH on {weather.route} ({weather.disruption_days_next_7} disrupted day(s) in the "
            f"next 7), but the network agent recommends increasing frequency."
        )
    market = recs.get("MARKET")
    if (
        market is not None
        and recs["NETWORK"].action == "INCREASE_FREQUENCY"
        and (market.demand_outlook == "WEAK" or market.competition_level == "HIGH")
    ):
        reasons = [
            reason
            for flagged, reason in (
                (market.demand_outlook == "WEAK", "the demand outlook is WEAK"),
                (market.competition_level == "HIGH", f"competition is HIGH ({market.rival_airlines} rival airlines)"),
            )
            if flagged
        ]
        warnings.append(
            f"Market agent warns about {market.route}: {' and '.join(reasons)}, but the network agent "
            f"recommends increasing frequency."
        )
    for agent_type, recommendation in recs.items():
        if recommendation.confidence < LOW_CONFIDENCE:
            warnings.append(f"{agent_type} agent has low confidence ({recommendation.confidence:.2f}).")
    return warnings


def weighted_confidence(recs: Mapping[str, BaseModel], weights: DecisionWeights) -> float:
    """Agent-weighted mean confidence over the agents present (plain mean if their weights sum to 0)."""
    total = sum(weights.agent_confidence[agent_type] for agent_type in recs)
    if total <= 0:
        return sum(r.confidence for r in recs.values()) / len(recs)
    return sum(weights.agent_confidence[t] * r.confidence for t, r in recs.items()) / total


def compute_score(factor_values: Mapping[str, float], weights: DecisionWeights) -> tuple[float, dict]:
    """Score 0-100 and the per-factor breakdown. `weight` is the factor's normalised share of the score."""
    total = sum(weights.factors.values())
    breakdown = {}
    score = 0.0
    for factor, value in factor_values.items():
        share = weights.factors[factor] / total
        breakdown[factor] = {"weight": share, "value": value, "contribution": 100 * share * value}
        score += 100 * share * value
    return score, breakdown


def verdict_for(score: float, blocking: int, weights: DecisionWeights) -> str:
    if blocking:
        return "REJECT"
    if score >= weights.thresholds["recommend"]:
        return "RECOMMEND"
    if score >= weights.thresholds["review"]:
        return "REVIEW"
    return "REJECT"


def risk_level(blocking: int, warnings: int, min_confidence: float) -> str:
    if blocking:
        return "HIGH"
    if warnings or min_confidence < MEDIUM_RISK_CONFIDENCE:
        return "MEDIUM"
    return "LOW"


def reconcile_all(
    recommendations: Mapping[str, BaseModel], *, weights: DecisionWeights, evidence_reliability: float | None,
    proposed_change: Mapping[str, str] | None = None,
) -> dict:
    """Combine every agent's recommendation into a Decision-shaped dict with a weighted 0-100 score.

    NETWORK and FLEET are required; MAINTENANCE, CREW, CARGO, WEATHER, FINANCE and EMISSIONS are optional and only
    checked when present. WEATHER, FINANCE and EMISSIONS add no money: they contribute a route check and a warning
    (FINANCE is sensitivity, not cash).
    Costs are summed without double counting because the fleet and crew agents' expected_cost_impact covers
    only the extra cost of making the resource available, and the cargo agent's excludes the flying cost
    (see the schema field descriptions). Cargo money counts only when the cargo agent analysed the same route.

    The caller (orchestrator) must add `run_id` and `agents_involved` before constructing
    a Decision ORM row, since this function has no notion of the run or agent execution ids.
    """
    for required in ("NETWORK", "FLEET"):
        if required not in recommendations:
            raise ValueError(f"{required} recommendation is required")
    recs = dict(recommendations)
    network, fleet, crew, cargo = recs["NETWORK"], recs["FLEET"], recs.get("CREW"), recs.get("CARGO")

    cargo_counts = cargo is not None and cargo.route == network.route
    revenue = network.expected_revenue_impact + (cargo.expected_revenue_impact if cargo_counts else 0.0)
    cost = network.expected_cost_impact + fleet.expected_cost_impact
    cost += crew.expected_cost_impact if crew is not None else 0.0
    cost += cargo.expected_cost_impact if cargo_counts else 0.0
    profit = revenue - cost

    checks = _checks(recs, profit)
    if proposed_change is not None:
        # The objective proposed this exact change: answering a different one would score the agent's
        # alternative instead of the user's suggestion.
        asked = (proposed_change["route"], proposed_change["action"])
        answered = (network.route, network.action)
        checks.append((
            "network_evaluates_proposed_change",
            f"The objective proposes {asked[1]} on {asked[0]}, but the network agent evaluated "
            f"{answered[1]} on {answered[0]}." if answered != asked else None,
        ))
    conflicts = [message for _, message in checks if message]
    warnings = _warnings(recs)
    passed = sum(1 for _, message in checks if message is None)

    factor_values = {
        "profit": sigmoid(profit / weights.profit_scale_usd),
        "confidence": weighted_confidence(recs, weights),
        "feasibility": passed / len(checks),
        "risk": 1.0 - min(1.0, BLOCKING_RISK_PENALTY * len(conflicts) + WARNING_RISK_PENALTY * len(warnings)),
        "data_quality": NEUTRAL_DATA_QUALITY if evidence_reliability is None else evidence_reliability,
    }
    score, breakdown = compute_score(factor_values, weights)
    score = round(score, 2)
    min_confidence = min(r.confidence for r in recs.values())

    return {
        "summary": f"{_ACTION_WORDS[network.action]} {network.route} frequency",
        "expected_profit_impact": profit,
        "expected_revenue_impact": revenue,
        "expected_cost_impact": cost,
        "confidence": min_confidence,
        "risks": list(dict.fromkeys(risk for r in recs.values() for risk in r.risks)),
        "constraints_checked": [name for name, _ in checks],
        "validation_result": {
            "schema": "PASS",
            "constraints": "FAIL" if conflicts else "PASS",
            "conflicts": conflicts,
            "risk": risk_level(len(conflicts), len(warnings), min_confidence),
            "score": score,
            "verdict": verdict_for(score, len(conflicts), weights),
            "warnings": warnings,
            "score_breakdown": breakdown,
        },
        "status": "RECOMMENDED",
    }
