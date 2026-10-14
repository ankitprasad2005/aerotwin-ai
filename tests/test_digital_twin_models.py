from sqlalchemy import select

from app.models.digital_twin import Airport, Aircraft, MaintenanceRecord, Route, Flight, PassengerDemand


async def test_airport_round_trip(db_session):
    airport = Airport(code="BOM", name="Chhatrapati Shivaji Maharaj", city="Mumbai", country="India")
    db_session.add(airport)
    await db_session.flush()

    result = await db_session.execute(select(Airport).where(Airport.code == "BOM"))
    fetched = result.scalar_one()
    assert fetched.city == "Mumbai"


async def test_aircraft_route_flight_relationships(db_session):
    bom = Airport(code="BOM", name="Mumbai", city="Mumbai", country="India")
    dele = Airport(code="DEL", name="Delhi", city="Delhi", country="India")
    db_session.add_all([bom, dele])
    await db_session.flush()

    route = Route(origin_id=bom.id, destination_id=dele.id, distance_km=1150, current_frequency=7)
    aircraft = Aircraft(
        tail_number="VT-AER1",
        aircraft_type="A320",
        location_id=bom.id,
        status="AVAILABLE",
        fuel_level_pct=72.0,
        flight_hours=4281.0,
        maintenance_status="NORMAL",
    )
    db_session.add_all([route, aircraft])
    await db_session.flush()

    flight = Flight(route_id=route.id, aircraft_id=aircraft.id, status="SCHEDULED")
    demand = PassengerDemand(route_id=route.id, period="2026-Q3", demand=18000, historical_load_factor=0.81)
    db_session.add_all([flight, demand])
    await db_session.flush()

    assert flight.route_id == route.id
    assert demand.route_id == route.id


async def test_airport_code_is_required(db_session):
    from sqlalchemy.exc import IntegrityError

    airport = Airport(code=None, name="No Code", city="Nowhere", country="Nowhere")
    db_session.add(airport)
    try:
        await db_session.flush()
        assert False, "expected IntegrityError for missing code"
    except IntegrityError:
        await db_session.rollback()


async def test_maintenance_record_round_trip_with_defaults(db_session):
    bom = Airport(code="BOM", name="Mumbai", city="Mumbai", country="India")
    db_session.add(bom)
    await db_session.flush()
    aircraft = Aircraft(
        tail_number="VT-AER1", aircraft_type="A320", location_id=bom.id, status="AVAILABLE",
        fuel_level_pct=72.0, flight_hours=4281.0, maintenance_status="NORMAL",
    )
    db_session.add(aircraft)
    await db_session.flush()

    record = MaintenanceRecord(
        aircraft_id=aircraft.id, check_type="A_CHECK", status="SCHEDULED", due_at_flight_hours=4350.0
    )
    db_session.add(record)
    await db_session.flush()

    fetched = (await db_session.execute(select(MaintenanceRecord))).scalar_one()
    assert fetched.aircraft_id == aircraft.id
    assert fetched.open_defects == 0
    assert fetched.notes == ""
