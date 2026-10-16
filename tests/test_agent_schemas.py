import pytest
from pydantic import ValidationError

from app.agents.schemas import CargoRecommendation, CrewRecommendation, FinanceRecommendation, FleetRecommendation, MaintenanceAction, MaintenanceRecommendation, NetworkRecommendation


def test_network_recommendation_round_trip():
    rec = NetworkRecommendation(
        route="BOM-DEL", action="INCREASE_FREQUENCY", expected_profit_impact=1.0,
        expected_revenue_impact=2.0, expected_cost_impact=3.0, confidence=0.5,
        risks=[], reasoning="x", cited_sources=[],
    )
    assert rec.action == "INCREASE_FREQUENCY"


def test_network_recommendation_rejects_invalid_action():
    with pytest.raises(ValidationError):
        NetworkRecommendation(
            route="BOM-DEL", action="DO_SOMETHING_ELSE", expected_profit_impact=1.0,
            expected_revenue_impact=2.0, expected_cost_impact=3.0, confidence=0.5,
            risks=[], reasoning="x", cited_sources=[],
        )


def test_network_recommendation_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        NetworkRecommendation(
            route="BOM-DEL", action="MAINTAIN", expected_profit_impact=1.0,
            expected_revenue_impact=2.0, expected_cost_impact=3.0, confidence=1.5,
            risks=[], reasoning="x", cited_sources=[],
        )


def test_fleet_recommendation_round_trip():
    rec = FleetRecommendation(
        route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="NO_CHANGE",
        aircraft_availability="AVAILABLE", expected_cost_impact=0.0, confidence=0.9,
        risks=[], reasoning="x", cited_sources=[],
    )
    assert rec.aircraft_availability == "AVAILABLE"


def test_fleet_recommendation_rejects_invalid_availability():
    with pytest.raises(ValidationError):
        FleetRecommendation(
            route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="NO_CHANGE",
            aircraft_availability="MAYBE", expected_cost_impact=0.0, confidence=0.9,
            risks=[], reasoning="x", cited_sources=[],
        )


def test_fleet_recommendation_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        FleetRecommendation(
            route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="NO_CHANGE",
            aircraft_availability="AVAILABLE", expected_cost_impact=0.0, confidence=-0.1,
            risks=[], reasoning="x", cited_sources=[],
        )


def _maintenance(**overrides):
    fields = dict(
        grounded_aircraft=["VT-AER3"], at_risk_aircraft=["VT-AER1"],
        actions=[{"tail_number": "VT-AER3", "action": "KEEP_GROUNDED", "reason": "Heavy check in progress."}],
        confidence=0.9, risks=["parts delay"], reasoning="Classified from the maintenance tool result.", cited_sources=[],
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
        risks=["duty limits"], reasoning="A captain and first officer are available at the origin.", cited_sources=[],
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


def _cargo(**overrides):
    fields = dict(
        route="BOM-DEL", cargo_stance="SUPPORTS", expected_revenue_impact=2040.0, expected_cost_impact=510.0,
        confidence=0.8, risks=["freight demand volatility"], reasoning="Unmet cargo demand fills the extra flight.", cited_sources=[],
    )
    fields.update(overrides)
    return CargoRecommendation(**fields)


def test_cargo_recommendation_round_trip():
    rec = _cargo()
    assert rec.cargo_stance == "SUPPORTS"
    assert rec.model_dump()["expected_revenue_impact"] == 2040.0


def test_cargo_recommendation_allows_negative_impacts_and_no_risks():
    rec = _cargo(cargo_stance="OPPOSES", expected_revenue_impact=-2040.0, expected_cost_impact=-510.0, risks=[])
    assert rec.expected_cost_impact == -510.0


@pytest.mark.parametrize("field, value", [("cargo_stance", "LOVES"), ("confidence", -0.1), ("confidence", 1.1)])
def test_cargo_recommendation_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _cargo(**{field: value})


@pytest.mark.parametrize("missing", [
    "route", "cargo_stance", "expected_revenue_impact", "expected_cost_impact", "confidence", "risks", "reasoning",
])
def test_cargo_recommendation_requires_every_field(missing):
    fields = _cargo().model_dump()
    del fields[missing]
    with pytest.raises(ValidationError):
        CargoRecommendation(**fields)


def _finance(**overrides):
    fields = dict(
        route="BOM-DEL", break_even_fuel_price_usd_per_gallon=3.77, fuel_headroom_pct=71.43,
        profit_change_if_fuel_up_10pct_usd=-280.0, profit_change_if_inr_weakens_5pct_usd=-476.19,
        financial_risk="LOW", confidence=0.8, risks=["fuel volatility"], reasoning="r", cited_sources=[],
    )
    fields.update(overrides)
    return FinanceRecommendation(**fields)


def test_finance_recommendation_round_trip_and_exact_field_names():
    rec = _finance()
    assert list(rec.model_dump()) == [
        "route", "break_even_fuel_price_usd_per_gallon", "fuel_headroom_pct", "profit_change_if_fuel_up_10pct_usd",
        "profit_change_if_inr_weakens_5pct_usd", "financial_risk", "confidence", "risks", "reasoning", "cited_sources",
    ]
    assert rec.profit_change_if_fuel_up_10pct_usd == -280.0


def test_finance_recommendation_allows_null_break_even_and_headroom():
    rec = _finance(break_even_fuel_price_usd_per_gallon=None, fuel_headroom_pct=None, risks=[])
    assert rec.fuel_headroom_pct is None


@pytest.mark.parametrize("field, value", [("financial_risk", "SEVERE"), ("confidence", -0.1), ("confidence", 1.1)])
def test_finance_recommendation_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        _finance(**{field: value})


@pytest.mark.parametrize("missing", [
    "route", "break_even_fuel_price_usd_per_gallon", "fuel_headroom_pct", "profit_change_if_fuel_up_10pct_usd",
    "profit_change_if_inr_weakens_5pct_usd", "financial_risk", "confidence", "risks", "reasoning", "cited_sources",
])
def test_finance_recommendation_requires_every_field(missing):
    fields = _finance().model_dump()
    del fields[missing]
    with pytest.raises(ValidationError):
        FinanceRecommendation(**fields)


def test_finance_field_descriptions_say_to_copy_the_network_routes_values():
    for name in ("break_even_fuel_price_usd_per_gallon", "fuel_headroom_pct", "profit_change_if_fuel_up_10pct_usd",
                 "profit_change_if_inr_weakens_5pct_usd", "financial_risk"):
        description = FinanceRecommendation.model_fields[name].description
        assert "Copy" in description and "NETWORK entry's route and action" in description


# --- cited_sources ----------------------------------------------------------------------------

_VALID = {
    NetworkRecommendation: dict(
        route="BOM-DEL", action="MAINTAIN", expected_profit_impact=0, expected_revenue_impact=0,
        expected_cost_impact=0, confidence=0.5, risks=[], reasoning="x",
    ),
    FleetRecommendation: dict(
        route="BOM-DEL", aircraft_tail_number="VT-AER1", assignment_action="NO_CHANGE",
        aircraft_availability="AVAILABLE", expected_cost_impact=0.0, confidence=0.9, risks=[], reasoning="x",
    ),
    MaintenanceRecommendation: dict(
        grounded_aircraft=[], at_risk_aircraft=[], actions=[], confidence=0.9, risks=[], reasoning="x",
    ),
    CrewRecommendation: dict(
        route="BOM-DEL", crew_availability="SUFFICIENT", assignment_action="NO_CHANGE", assigned_crew=[],
        expected_cost_impact=0.0, confidence=0.9, risks=[], reasoning="x",
    ),
    CargoRecommendation: dict(
        route="BOM-DEL", cargo_stance="NEUTRAL", expected_revenue_impact=0, expected_cost_impact=0,
        confidence=0.9, risks=[], reasoning="x",
    ),
}


@pytest.mark.parametrize("schema", list(_VALID))
def test_cited_sources_is_required_on_every_schema(schema):
    with pytest.raises(ValidationError):
        schema(**_VALID[schema])
    assert schema(**_VALID[schema], cited_sources=[]).cited_sources == []
    assert "cited_sources" in schema.model_json_schema()["required"]  # strict structured outputs need it


@pytest.mark.parametrize("schema", list(_VALID))
def test_cited_sources_keeps_ids_and_rejects_non_lists(schema):
    assert schema(**_VALID[schema], cited_sources=["fuel:eia:2026-10-10", "web:3f9a1c2e"]).cited_sources == [
        "fuel:eia:2026-10-10", "web:3f9a1c2e",
    ]
    with pytest.raises(ValidationError):
        schema(**_VALID[schema], cited_sources="fuel:eia:2026-10-10")
    with pytest.raises(ValidationError):
        schema(**_VALID[schema], cited_sources=[1])
