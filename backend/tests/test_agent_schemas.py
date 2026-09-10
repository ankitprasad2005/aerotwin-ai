import pytest
from pydantic import ValidationError

from app.agents.schemas import FleetRecommendation, NetworkRecommendation


def test_network_recommendation_round_trip():
    rec = NetworkRecommendation(
        route="BOM-DEL", action="INCREASE_FREQUENCY", expected_profit_impact=1.0,
        expected_revenue_impact=2.0, expected_cost_impact=3.0, confidence=0.5,
        risks=[], reasoning="x",
    )
    assert rec.action == "INCREASE_FREQUENCY"


def test_network_recommendation_rejects_invalid_action():
    with pytest.raises(ValidationError):
        NetworkRecommendation(
            route="BOM-DEL", action="DO_SOMETHING_ELSE", expected_profit_impact=1.0,
            expected_revenue_impact=2.0, expected_cost_impact=3.0, confidence=0.5,
            risks=[], reasoning="x",
        )


def test_network_recommendation_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        NetworkRecommendation(
            route="BOM-DEL", action="MAINTAIN", expected_profit_impact=1.0,
            expected_revenue_impact=2.0, expected_cost_impact=3.0, confidence=1.5,
            risks=[], reasoning="x",
        )


def test_fleet_recommendation_round_trip():
    rec = FleetRecommendation(
        route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="NO_CHANGE",
        aircraft_availability="AVAILABLE", expected_cost_impact=0.0, confidence=0.9,
        risks=[], reasoning="x",
    )
    assert rec.aircraft_availability == "AVAILABLE"


def test_fleet_recommendation_rejects_invalid_availability():
    with pytest.raises(ValidationError):
        FleetRecommendation(
            route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="NO_CHANGE",
            aircraft_availability="MAYBE", expected_cost_impact=0.0, confidence=0.9,
            risks=[], reasoning="x",
        )


def test_fleet_recommendation_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        FleetRecommendation(
            route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="NO_CHANGE",
            aircraft_availability="AVAILABLE", expected_cost_impact=0.0, confidence=-0.1,
            risks=[], reasoning="x",
        )
