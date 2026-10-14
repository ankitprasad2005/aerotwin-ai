from sqlalchemy import select
import pytest

from app.models.digital_twin import Aircraft, Airport, MaintenanceRecord
from app.seed.seed import run_seed
from app.tools.digital_twin_tools import (
    DUE_SOON_HOURS,
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
