import pytest
from pydantic import ValidationError

from app.agents.schemas import CrewRecommendation, FleetRecommendation, MaintenanceAction, MaintenanceRecommendation, NetworkRecommendation


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


def _maintenance(**overrides):
    fields = dict(
        grounded_aircraft=["VT-AER3"], at_risk_aircraft=["VT-AER1"],
        actions=[{"tail_number": "VT-AER3", "action": "KEEP_GROUNDED", "reason": "Heavy check in progress."}],
        confidence=0.9, risks=["parts delay"], reasoning="Classified from the maintenance tool result.",
    )
    fields.update(overrides)
    return MaintenanceRecommendation(**fields)


def test_maintenance_recommendation_round_trip():
    rec = _maintenance()
    assert rec.grounded_aircraft == ["VT-AER3"]
    assert isinstance(rec.actions[0], MaintenanceAction)
    assert rec.model_dump()["actions"][0]["action"] == "KEEP_GROUNDED"


def test_maintenance_recommendation_allows_empty_lists():
    rec = _maintenance(grounded_aircraft=[], at_risk_aircraft=[], actions=[], risks=[])
    assert rec.actions == []


@pytest.mark.parametrize("action", ["SCHEDULE_CHECK", "MONITOR", "KEEP_GROUNDED", "RELEASE"])
def test_maintenance_action_accepts_each_valid_action(action):
    assert MaintenanceAction(tail_number="VT-AER1", action=action, reason="r").action == action


def test_maintenance_action_rejects_invalid_action():
    with pytest.raises(ValidationError):
        MaintenanceAction(tail_number="VT-AER1", action="SCRAP", reason="r")


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_maintenance_recommendation_rejects_confidence_out_of_range(confidence):
    with pytest.raises(ValidationError):
        _maintenance(confidence=confidence)


@pytest.mark.parametrize("missing", ["grounded_aircraft", "at_risk_aircraft", "actions", "confidence", "risks", "reasoning"])
def test_maintenance_recommendation_requires_every_field(missing):
    fields = _maintenance().model_dump()
    del fields[missing]
    with pytest.raises(ValidationError):
        MaintenanceRecommendation(**fields)


def _crew(**overrides):
    fields = dict(
        route="BOM-DEL", crew_availability="SUFFICIENT", assignment_action="ASSIGN_ADDITIONAL_CREW",
        assigned_crew=["CR-001", "CR-003"], expected_cost_impact=0.0, confidence=0.85,
        risks=["duty limits"], reasoning="A captain and first officer are available at the origin.",
    )
    fields.update(overrides)
    return CrewRecommendation(**fields)


def test_crew_recommendation_round_trip():
    rec = _crew()
    assert rec.assigned_crew == ["CR-001", "CR-003"]
    assert rec.model_dump()["assignment_action"] == "ASSIGN_ADDITIONAL_CREW"


def test_crew_recommendation_allows_no_crew_and_no_risks():
    rec = _crew(assignment_action="NO_CHANGE", assigned_crew=[], risks=[])
    assert rec.assigned_crew == []


@pytest.mark.parametrize("field, value", [
    ("crew_availability", "MAYBE"), ("assignment_action", "HIRE"), ("confidence", -0.1), ("confidence", 1.1),
])
def test_crew_recommendation_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _crew(**{field: value})


@pytest.mark.parametrize("missing", [
    "route", "crew_availability", "assignment_action", "assigned_crew", "expected_cost_impact", "confidence",
    "risks", "reasoning",
])
def test_crew_recommendation_requires_every_field(missing):
    fields = _crew().model_dump()
    del fields[missing]
    with pytest.raises(ValidationError):
        CrewRecommendation(**fields)
