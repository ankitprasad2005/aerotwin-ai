from sqlalchemy import select
import pytest

from app.models.digital_twin import Aircraft, Airport, CargoDemand, CrewMember, MaintenanceRecord, Route
from app.seed.seed import run_seed
from app.tools.digital_twin_tools import (
    DUE_SOON_HOURS,
    MAX_CARGO_LOAD_FACTOR,
    MIN_USABLE_DUTY_HOURS,
    query_cargo_opportunities,
    weekly_cargo_change_impact,
    classify_crew_availability,
    query_crew_status,
    classify_airworthiness,
    query_fleet_status,
    query_maintenance_status,
    query_route_profitability,
    weekly_frequency_change_impact,
)


async def test_query_route_profitability_empty_db_returns_empty_list(db_session):
    result = await query_route_profitability(db_session)
    assert result == {"routes": []}


async def test_query_route_profitability_returns_seeded_routes(db_session):
    await run_seed(db_session)

    result = await query_route_profitability(db_session)

    routes = {r["route"]: r for r in result["routes"]}
    assert "BOM-DEL" in routes
    assert routes["BOM-DEL"]["current_frequency"] == 7
    assert routes["BOM-DEL"]["demand"] == 18000


async def test_query_route_profitability_includes_economics_and_weekly_impacts(db_session):
    await run_seed(db_session)

    result = await query_route_profitability(db_session)

    bom_del = {r["route"]: r for r in result["routes"]}["BOM-DEL"]
    assert bom_del["seats_per_flight"] == 180
    assert bom_del["average_fare_usd"] == 95.0
    assert bom_del["operating_cost_per_flight_usd"] == 9000.0
    # 7 flights x 180 seats x 0.81 = 1020.6 passengers x $95 = $96,957 revenue, minus 7 x $9,000.
    assert bom_del["weekly_profit_usd"] == 33957
    # Weekly demand 18000 / 13 = 1384.6 exceeds 8 flights' 90% ceiling (1296), so +275.4 passengers.
    assert bom_del["impact_if_increase_by_one_weekly_flight"] == {
        "revenue_usd": 26163, "cost_usd": 9000, "profit_usd": 17163, "projected_load_factor": 0.9,
    }
    # 6 flights fit only 972 of today's 1020.6 passengers at the 90% ceiling: lose 48.6 x $95, save $9,000.
    assert bom_del["impact_if_decrease_by_one_weekly_flight"] == {
        "revenue_usd": -4617, "cost_usd": -9000, "profit_usd": 4383, "projected_load_factor": 0.9,
    }


async def test_query_fleet_status_returns_seeded_aircraft(db_session):
    await run_seed(db_session)

    result = await query_fleet_status(db_session)

    tails = {a["tail_number"]: a for a in result["aircraft"]}
    assert "VT-AER3" in tails
    assert tails["VT-AER3"]["status"] == "MAINTENANCE"


async def test_query_route_profitability_handles_route_without_demand_row(db_session):
    from app.models.digital_twin import Airport, Route

    origin = Airport(code="XYZ", name="Test Origin", city="Testville", country="Testland")
    destination = Airport(code="ABC", name="Test Dest", city="Testburg", country="Testland")
    db_session.add_all([origin, destination])
    await db_session.flush()

    route = Route(origin_id=origin.id, destination_id=destination.id, distance_km=500, current_frequency=1)
    db_session.add(route)
    await db_session.flush()

    result = await query_route_profitability(db_session)

    routes = {r["route"]: r for r in result["routes"]}
    assert routes["XYZ-ABC"]["demand"] is None
    assert routes["XYZ-ABC"]["historical_load_factor"] is None
    assert routes["XYZ-ABC"]["weekly_profit_usd"] is None
    assert routes["XYZ-ABC"]["impact_if_increase_by_one_weekly_flight"] is None
    assert routes["XYZ-ABC"]["impact_if_decrease_by_one_weekly_flight"] is None


async def test_query_route_profitability_skips_impacts_when_route_economics_are_missing(db_session):
    from app.models.digital_twin import Airport, PassengerDemand, Route

    origin = Airport(code="XYZ", name="Test Origin", city="Testville", country="Testland")
    destination = Airport(code="ABC", name="Test Dest", city="Testburg", country="Testland")
    db_session.add_all([origin, destination])
    await db_session.flush()
    route = Route(origin_id=origin.id, destination_id=destination.id, distance_km=500, current_frequency=3)
    db_session.add(route)
    await db_session.flush()
    db_session.add(PassengerDemand(route_id=route.id, period="2026-Q3", demand=4000, historical_load_factor=0.7))
    await db_session.flush()

    result = await query_route_profitability(db_session)

    entry = result["routes"][0]
    assert entry["demand"] == 4000
    assert entry["weekly_profit_usd"] is None
    assert entry["impact_if_increase_by_one_weekly_flight"] is None


def _impact(**overrides):
    inputs = dict(
        current_frequency=3, seats_per_flight=180, historical_load_factor=0.55, quarterly_demand=4100,
        average_fare_usd=50.0, operating_cost_per_flight_usd=4800.0,
    )
    inputs.update(overrides)
    return weekly_frequency_change_impact(**inputs)


def test_increase_is_limited_by_weekly_demand():
    # Weekly demand 4100 / 13 = 315.4 vs today's 297 passengers: only 18.4 more to capture, and
    # spreading 315.4 passengers over 4 x 180 seats drops the load factor below 50%.
    assert _impact(change=1) == {
        "revenue_usd": 919, "cost_usd": 4800, "profit_usd": -3881, "projected_load_factor": 0.438,
    }


def test_decrease_keeps_passengers_that_still_fit_and_saves_the_flight_cost():
    # 297 passengers still fit in 2 x 180 seats at the 90% ceiling (324), so no revenue is lost.
    assert _impact(change=-1) == {
        "revenue_usd": 0, "cost_usd": -4800, "profit_usd": 4800, "projected_load_factor": 0.825,
    }


def test_decrease_never_adds_passengers_even_with_unmet_demand():
    impact = _impact(historical_load_factor=0.5, quarterly_demand=100000, change=-1)
    assert impact["revenue_usd"] == 0


def test_decrease_to_zero_flights_returns_none():
    assert _impact(current_frequency=1, change=-1) is None


def _item(hours_until_due=500.0, status="SCHEDULED", defects=0):
    return {"status": status, "hours_until_due": hours_until_due, "overdue": hours_until_due < 0, "open_defects": defects}


def test_due_soon_threshold_is_100_flight_hours():
    assert DUE_SOON_HOURS == 100.0


@pytest.mark.parametrize(
    "aircraft_status, items, expected",
    [
        ("AVAILABLE", [], "SERVICEABLE"),
        ("AVAILABLE", [_item(500.0)], "SERVICEABLE"),
        ("AVAILABLE", [_item(101.0)], "SERVICEABLE"),
        ("AVAILABLE", [_item(100.0)], "DUE_SOON"),
        ("AVAILABLE", [_item(0.0)], "DUE_SOON"),
        ("AVAILABLE", [_item(500.0, defects=1)], "DUE_SOON"),
        ("AVAILABLE", [_item(-0.5)], "GROUNDED"),
        ("AVAILABLE", [_item(500.0, status="IN_PROGRESS")], "GROUNDED"),
        ("MAINTENANCE", [], "GROUNDED"),
        ("MAINTENANCE", [_item(500.0)], "GROUNDED"),
        ("AVAILABLE", [_item(500.0), _item(50.0)], "DUE_SOON"),
        ("AVAILABLE", [_item(50.0), _item(-10.0)], "GROUNDED"),
    ],
)
def test_classify_airworthiness(aircraft_status, items, expected):
    assert classify_airworthiness(aircraft_status, items) == expected


async def test_query_maintenance_status_empty_db_returns_empty_list(db_session):
    assert await query_maintenance_status(db_session) == {"maintenance": []}


async def test_query_maintenance_status_classifies_seeded_aircraft(db_session):
    await run_seed(db_session)

    result = await query_maintenance_status(db_session)

    by_tail = {a["tail_number"]: a for a in result["maintenance"]}
    assert list(by_tail) == ["VT-AER1", "VT-AER2", "VT-AER3", "VT-AER4"]  # ordered by tail number
    assert {t: a["airworthiness"] for t, a in by_tail.items()} == {
        "VT-AER1": "DUE_SOON", "VT-AER2": "SERVICEABLE", "VT-AER3": "GROUNDED", "VT-AER4": "SERVICEABLE",
    }
    aer1 = by_tail["VT-AER1"]
    assert aer1["open_items"][0]["hours_until_due"] == pytest.approx(69.0)
    assert aer1["next_due_in_hours"] == pytest.approx(69.0)
    assert aer1["total_open_defects"] == 0
    aer3 = by_tail["VT-AER3"]
    assert aer3["open_items"][0]["overdue"] is True
    assert aer3["total_open_defects"] == 2


async def test_query_maintenance_status_ignores_completed_items(db_session):
    await run_seed(db_session)

    result = await query_maintenance_status(db_session)

    aer2 = next(a for a in result["maintenance"] if a["tail_number"] == "VT-AER2")
    assert [i["check_type"] for i in aer2["open_items"]] == ["A_CHECK"]  # the COMPLETED C_CHECK is history
    assert aer2["next_due_in_hours"] == pytest.approx(490.0)


async def test_query_maintenance_status_aircraft_without_records_is_serviceable(db_session):
    airport = Airport(code="BOM", name="x", city="x", country="x")
    db_session.add(airport)
    await db_session.flush()
    db_session.add(Aircraft(
        tail_number="VT-NEW", aircraft_type="A320", location_id=airport.id, status="AVAILABLE",
        fuel_level_pct=90.0, flight_hours=10.0, maintenance_status="NORMAL",
    ))
    await db_session.flush()

    result = await query_maintenance_status(db_session)

    assert result["maintenance"][0]["open_items"] == []
    assert result["maintenance"][0]["next_due_in_hours"] is None
    assert result["maintenance"][0]["airworthiness"] == "SERVICEABLE"


async def test_query_maintenance_status_next_due_is_the_soonest_open_item(db_session):
    await run_seed(db_session)
    aircraft = (await db_session.execute(
        select(Aircraft).where(Aircraft.tail_number == "VT-AER4")
    )).scalar_one()
    db_session.add(MaintenanceRecord(
        aircraft_id=aircraft.id, check_type="ENGINE_INSPECTION", status="SCHEDULED",
        due_at_flight_hours=800.0, open_defects=1,
    ))
    await db_session.flush()

    result = await query_maintenance_status(db_session)

    aer4 = next(a for a in result["maintenance"] if a["tail_number"] == "VT-AER4")
    assert aer4["next_due_in_hours"] == pytest.approx(160.0)
    assert [i["check_type"] for i in aer4["open_items"]] == ["ENGINE_INSPECTION", "A_CHECK"]
    assert aer4["total_open_defects"] == 1
    assert aer4["airworthiness"] == "DUE_SOON"  # an open defect alone makes it due soon


def test_min_usable_duty_hours_is_10():
    assert MIN_USABLE_DUTY_HOURS == 10.0


@pytest.mark.parametrize(
    "status, remaining, expected",
    [
        ("AVAILABLE", 40.0, "AVAILABLE"),
        ("AVAILABLE", 10.0, "AVAILABLE"),
        ("AVAILABLE", 9.99, "LIMITED"),
        ("AVAILABLE", 0.01, "LIMITED"),
        ("AVAILABLE", 0.0, "UNAVAILABLE"),
        ("AVAILABLE", -5.0, "UNAVAILABLE"),  # over the weekly limit
        ("ON_LEAVE", 40.0, "UNAVAILABLE"),
        ("SICK", 25.0, "UNAVAILABLE"),
    ],
)
def test_classify_crew_availability(status, remaining, expected):
    assert classify_crew_availability(status, remaining) == expected


async def test_query_crew_status_empty_db_returns_empty_list(db_session):
    assert await query_crew_status(db_session) == {"crew": []}


async def test_query_crew_status_describes_seeded_crew(db_session):
    await run_seed(db_session)

    crew = (await query_crew_status(db_session))["crew"]

    assert [m["employee_code"] for m in crew] == [f"CR-00{i}" for i in range(1, 10)]
    by_code = {m["employee_code"]: m for m in crew}
    assert {c: m["availability"] for c, m in by_code.items()} == {
        "CR-001": "AVAILABLE", "CR-002": "LIMITED", "CR-003": "AVAILABLE", "CR-004": "AVAILABLE",
        "CR-005": "UNAVAILABLE", "CR-006": "AVAILABLE", "CR-007": "UNAVAILABLE", "CR-008": "UNAVAILABLE",
        "CR-009": "AVAILABLE",
    }
    assert by_code["CR-001"] == {
        "employee_code": "CR-001", "name": "Arjun Mehta", "role": "CAPTAIN", "base": "BOM",
        "qualified_aircraft_type": "A320", "status": "AVAILABLE", "weekly_duty_hours": 22.0,
        "max_weekly_duty_hours": 40.0, "remaining_duty_hours": 18.0, "availability": "AVAILABLE",
    }
    assert by_code["CR-002"]["remaining_duty_hours"] == 4.0
    assert by_code["CR-008"]["remaining_duty_hours"] == 0.0


def _cargo_impact(**overrides):
    inputs = dict(
        current_frequency=7, capacity_kg_per_flight=2000.0, weekly_demand_kg=16000.0,
        rate_usd_per_kg=1.2, handling_cost_usd_per_kg=0.3, change=1,
    )
    inputs.update(overrides)
    return weekly_cargo_change_impact(**inputs)


def test_max_cargo_load_factor_is_85_percent():
    assert MAX_CARGO_LOAD_FACTOR == 0.85


def test_cargo_increase_captures_unmet_demand_up_to_the_new_ceiling():
    # 7 flights carry 11,900 kg (85% of 14,000); 8 flights can carry 13,600 kg of the 16,000 kg demand.
    assert _cargo_impact() == {"additional_kg": 1700, "revenue_usd": 2040, "cost_usd": 510, "profit_usd": 1530}


def test_cargo_increase_is_capped_by_demand():
    # 5 flights carry 7,650 kg; demand 8,000 kg is below the 6-flight ceiling (9,180 kg), so only 350 kg is added.
    result = _cargo_impact(current_frequency=5, capacity_kg_per_flight=1800.0, weekly_demand_kg=8000.0,
                           rate_usd_per_kg=1.0, handling_cost_usd_per_kg=0.2)
    assert result == {"additional_kg": 350, "revenue_usd": 350, "cost_usd": 70, "profit_usd": 280}


def test_cargo_increase_adds_nothing_when_demand_is_already_served():
    assert _cargo_impact(weekly_demand_kg=9000.0)["additional_kg"] == 0
    assert _cargo_impact(weekly_demand_kg=9000.0)["profit_usd"] == 0


def test_cargo_decrease_loses_the_cargo_that_no_longer_fits():
    # 6 flights carry at most 10,200 kg, so 1,700 kg of the 11,900 kg now carried is lost (revenue and handling).
    assert _cargo_impact(change=-1) == {
        "additional_kg": -1700, "revenue_usd": -2040, "cost_usd": -510, "profit_usd": -1530
    }


def test_cargo_decrease_loses_nothing_when_demand_still_fits():
    assert _cargo_impact(change=-1, weekly_demand_kg=9000.0)["additional_kg"] == 0


def test_cargo_change_that_removes_every_flight_is_not_a_frequency_change():
    assert _cargo_impact(current_frequency=1, change=-1) is None
    assert _cargo_impact(current_frequency=0, change=-1) is None


def test_cargo_increase_from_a_route_with_no_flights_carries_cargo_on_the_first_one():
    result = _cargo_impact(current_frequency=0, weekly_demand_kg=5000.0)
    assert result["additional_kg"] == 1700  # one flight: 2,000 x 0.85


def test_cargo_with_zero_capacity_per_flight_changes_nothing():
    assert _cargo_impact(capacity_kg_per_flight=0.0)["additional_kg"] == 0


async def _add_route_with_cargo(db_session, origin_code, dest_code, periods):
    airports = {}
    for code in (origin_code, dest_code):
        existing = (await db_session.execute(select(Airport).where(Airport.code == code))).scalar_one_or_none()
        if existing is None:
            existing = Airport(code=code, name=code, city=code, country="x")
            db_session.add(existing)
            await db_session.flush()
        airports[code] = existing
    route = Route(origin_id=airports[origin_code].id, destination_id=airports[dest_code].id,
                  distance_km=100, current_frequency=3)
    db_session.add(route)
    await db_session.flush()
    for period, demand in periods:
        db_session.add(CargoDemand(
            route_id=route.id, period=period, weekly_demand_kg=demand, capacity_kg_per_flight=1000.0,
            rate_usd_per_kg=2.0, handling_cost_usd_per_kg=0.5,
        ))
    await db_session.flush()
    return route


async def test_query_cargo_opportunities_empty_db_returns_empty_list(db_session):
    assert await query_cargo_opportunities(db_session) == {"cargo": []}


async def test_query_cargo_opportunities_describes_seeded_routes(db_session):
    await run_seed(db_session)

    cargo = (await query_cargo_opportunities(db_session))["cargo"]

    by_route = {c["route"]: c for c in cargo}
    assert set(by_route) == {"BOM-DEL", "DEL-BOM", "BOM-BLR", "BLR-HYD", "MAA-CCU"}
    bom_del = by_route["BOM-DEL"]
    assert bom_del["current_frequency"] == 7
    assert bom_del["period"] == "2026-Q3"
    assert bom_del["weekly_demand_kg"] == 16000.0
    assert bom_del["weekly_capacity_kg"] == 14000.0
    assert bom_del["weekly_carried_kg"] == pytest.approx(11900.0)
    assert bom_del["cargo_load_factor"] == 0.85
    assert bom_del["impact_if_increase_by_one_weekly_flight"] == {
        "additional_kg": 1700, "revenue_usd": 2040, "cost_usd": 510, "profit_usd": 1530
    }
    assert bom_del["impact_if_decrease_by_one_weekly_flight"]["profit_usd"] == -1530
    # An unconstrained route: demand already fits, so changing frequency moves no cargo.
    assert by_route["BLR-HYD"]["weekly_carried_kg"] == 2000.0
    assert by_route["BLR-HYD"]["impact_if_increase_by_one_weekly_flight"]["additional_kg"] == 0


async def test_query_cargo_opportunities_omits_routes_without_cargo_data(db_session):
    await run_seed(db_session)
    await _add_route_with_cargo(db_session, "BOM", "HYD", [])

    routes = {c["route"] for c in (await query_cargo_opportunities(db_session))["cargo"]}

    assert "BOM-HYD" not in routes
    assert len(routes) == 5


async def test_query_cargo_opportunities_uses_the_latest_period(db_session):
    await _add_route_with_cargo(db_session, "AAA", "BBB", [("2026-Q2", 100.0), ("2026-Q4", 2500.0), ("2026-Q3", 900.0)])

    (entry,) = (await query_cargo_opportunities(db_session))["cargo"]

    assert entry["route"] == "AAA-BBB"
    assert entry["period"] == "2026-Q4"
    assert entry["weekly_demand_kg"] == 2500.0


async def test_query_cargo_opportunities_handles_a_route_with_no_flights(db_session):
    route = await _add_route_with_cargo(db_session, "AAA", "BBB", [("2026-Q3", 800.0)])
    route.current_frequency = 0
    await db_session.flush()

    (entry,) = (await query_cargo_opportunities(db_session))["cargo"]

    assert entry["weekly_capacity_kg"] == 0.0
    assert entry["cargo_load_factor"] == 0.0  # no division by zero
    assert entry["impact_if_decrease_by_one_weekly_flight"] is None
