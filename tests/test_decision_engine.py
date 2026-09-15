from app.agents.schemas import FleetRecommendation, NetworkRecommendation
from app.decision.engine import reconcile


def _network(**overrides):
    base = dict(
        route="BOM-DEL", action="INCREASE_FREQUENCY", expected_profit_impact=125000.0,
        expected_revenue_impact=300000.0, expected_cost_impact=175000.0, confidence=0.82,
        risks=["fuel price volatility"], reasoning="Demand exceeds capacity.",
    )
    base.update(overrides)
    return NetworkRecommendation(**base)


def _fleet(**overrides):
    base = dict(
        route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="ASSIGN_ADDITIONAL_AIRCRAFT",
        aircraft_availability="AVAILABLE", expected_cost_impact=40000.0, confidence=0.88,
        risks=["crew scheduling"], reasoning="Aircraft available at origin.",
    )
    base.update(overrides)
    return FleetRecommendation(**base)


def test_reconcile_no_conflict_yields_low_risk_recommendation():
    decision = reconcile(_network(), _fleet())

    assert decision["status"] == "RECOMMENDED"
    assert decision["validation_result"]["conflicts"] == []
    assert decision["validation_result"]["constraints"] == "PASS"
    assert decision["validation_result"]["risk"] == "LOW"
    assert decision["summary"] == "Increase BOM-DEL frequency"
    assert decision["expected_cost_impact"] == 175000.0 + 40000.0
    assert decision["constraints_checked"] == [
        "aircraft_availability_matches_action",
        "network_and_fleet_route_match",
        "fleet_assignment_matches_network_action",
        "change_has_positive_expected_profit",
    ]


def test_reconcile_detects_aircraft_unavailable_conflict():
    decision = reconcile(_network(), _fleet(aircraft_availability="UNAVAILABLE"))

    assert len(decision["validation_result"]["conflicts"]) == 1
    assert decision["validation_result"]["constraints"] == "FAIL"
    assert decision["validation_result"]["risk"] == "HIGH"


def test_reconcile_detects_route_mismatch_conflict():
    decision = reconcile(_network(route="BOM-DEL"), _fleet(route="BLR-HYD"))

    assert any("route" in c.lower() for c in decision["validation_result"]["conflicts"])
    assert decision["validation_result"]["risk"] == "HIGH"


def test_reconcile_low_confidence_without_conflict_yields_medium_risk():
    decision = reconcile(_network(confidence=0.5), _fleet())

    assert decision["validation_result"]["conflicts"] == []
    assert decision["validation_result"]["risk"] == "MEDIUM"
    assert decision["confidence"] == 0.5  # min of both


def test_reconcile_deduplicates_shared_risks():
    decision = reconcile(_network(risks=["fuel price volatility"]), _fleet(risks=["fuel price volatility"]))

    assert decision["risks"] == ["fuel price volatility"]


def test_reconcile_conflict_takes_priority_over_low_confidence():
    decision = reconcile(
        _network(confidence=0.3),
        _fleet(confidence=0.3, aircraft_availability="UNAVAILABLE"),
    )

    assert decision["validation_result"]["conflicts"] != []
    assert decision["validation_result"]["risk"] == "HIGH"


def test_reconcile_profit_impact_accounts_for_combined_cost():
    decision = reconcile(_network(), _fleet())

    # revenue 300000, combined cost = 175000 (network) + 40000 (fleet) = 215000
    assert decision["expected_profit_impact"] == 300000.0 - 215000.0


def test_reconcile_detects_no_change_conflict_when_network_wants_increase():
    decision = reconcile(_network(action="INCREASE_FREQUENCY"), _fleet(assignment_action="NO_CHANGE"))

    assert any("no_change" in c.lower() or "nochange" in c.lower() for c in decision["validation_result"]["conflicts"])
    assert decision["validation_result"]["risk"] == "HIGH"


def test_reconcile_detects_unwarranted_additional_aircraft_conflict():
    decision = reconcile(
        _network(action="MAINTAIN"), _fleet(assignment_action="ASSIGN_ADDITIONAL_AIRCRAFT")
    )

    assert any("assign_additional_aircraft" in c.lower() for c in decision["validation_result"]["conflicts"])
    assert decision["validation_result"]["risk"] == "HIGH"


def test_reconcile_flags_a_change_that_loses_money_once_fleet_costs_are_included():
    # The live failure mode this guards against: an "increase" whose revenue doesn't cover its costs.
    decision = reconcile(
        _network(expected_revenue_impact=10000.0, expected_cost_impact=9000.0, expected_profit_impact=1000.0),
        _fleet(expected_cost_impact=1500.0),
    )

    assert decision["expected_profit_impact"] == -500.0
    assert any("profit" in c.lower() for c in decision["validation_result"]["conflicts"])
    assert decision["validation_result"]["constraints"] == "FAIL"
    assert decision["validation_result"]["risk"] == "HIGH"


def test_reconcile_flags_a_change_with_zero_expected_profit():
    decision = reconcile(
        _network(expected_revenue_impact=9000.0, expected_cost_impact=9000.0, expected_profit_impact=0.0),
        _fleet(expected_cost_impact=0.0),
    )

    assert any("profit" in c.lower() for c in decision["validation_result"]["conflicts"])


def test_reconcile_accepts_a_decrease_that_pays_off_through_cost_savings():
    decision = reconcile(
        _network(
            action="DECREASE_FREQUENCY", expected_revenue_impact=-4617.0, expected_cost_impact=-9000.0,
            expected_profit_impact=4383.0,
        ),
        _fleet(assignment_action="NO_CHANGE", expected_cost_impact=0.0),
    )

    assert decision["expected_profit_impact"] == 4383.0
    assert decision["validation_result"]["conflicts"] == []
    assert decision["summary"] == "Decrease BOM-DEL frequency"


def test_reconcile_does_not_flag_maintain_with_zero_impact():
    decision = reconcile(
        _network(action="MAINTAIN", expected_revenue_impact=0.0, expected_cost_impact=0.0, expected_profit_impact=0.0),
        _fleet(assignment_action="NO_CHANGE", expected_cost_impact=0.0),
    )

    assert decision["validation_result"]["conflicts"] == []
