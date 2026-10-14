from sqlalchemy import select, func

from app.models.digital_twin import Airport, Aircraft, CargoDemand, CrewMember, MaintenanceRecord, Route, Flight, PassengerDemand
from app.seed.seed import run_seed


async def test_seed_creates_expected_counts(db_session):
    await run_seed(db_session)

    airport_count = (await db_session.execute(select(func.count()).select_from(Airport))).scalar_one()
    aircraft_count = (await db_session.execute(select(func.count()).select_from(Aircraft))).scalar_one()
    route_count = (await db_session.execute(select(func.count()).select_from(Route))).scalar_one()
    demand_count = (await db_session.execute(select(func.count()).select_from(PassengerDemand))).scalar_one()

    assert airport_count == 6
    assert aircraft_count == 4
    assert route_count == 5
    assert demand_count == 5


async def test_seed_is_idempotent(db_session):
    await run_seed(db_session)
    await run_seed(db_session)

    airport_count = (await db_session.execute(select(func.count()).select_from(Airport))).scalar_one()
    assert airport_count == 6  # not doubled on second run


async def test_seed_creates_maintenance_records_linked_to_the_right_aircraft(db_session):
    await run_seed(db_session)

    rows = (
        await db_session.execute(
            select(Aircraft.tail_number, MaintenanceRecord.check_type, MaintenanceRecord.status,
                   MaintenanceRecord.due_at_flight_hours, MaintenanceRecord.open_defects)
            .join(MaintenanceRecord, MaintenanceRecord.aircraft_id == Aircraft.id)
            .order_by(Aircraft.tail_number, MaintenanceRecord.due_at_flight_hours)
        )
    ).all()

    assert rows == [
        ("VT-AER1", "A_CHECK", "SCHEDULED", 4350.0, 0),
        ("VT-AER2", "C_CHECK", "COMPLETED", 1800.0, 0),
        ("VT-AER2", "A_CHECK", "SCHEDULED", 2600.0, 0),
        ("VT-AER3", "C_CHECK", "IN_PROGRESS", 9050.0, 2),
        ("VT-AER4", "A_CHECK", "SCHEDULED", 1000.0, 0),
    ]


async def test_seed_does_not_duplicate_maintenance_records(db_session):
    await run_seed(db_session)
    await run_seed(db_session)

    count = (await db_session.execute(select(func.count()).select_from(MaintenanceRecord))).scalar_one()
    assert count == 5


async def test_seed_creates_crew_based_at_the_right_airports(db_session):
    await run_seed(db_session)

    rows = (
        await db_session.execute(
            select(CrewMember.employee_code, Airport.code, CrewMember.role, CrewMember.qualified_aircraft_type,
                   CrewMember.status, CrewMember.weekly_duty_hours)
            .join(Airport, Airport.id == CrewMember.base_id)
            .order_by(CrewMember.employee_code)
        )
    ).all()

    assert [r[0] for r in rows] == [f"CR-00{i}" for i in range(1, 10)]
    assert rows[0] == ("CR-001", "BOM", "CAPTAIN", "A320", "AVAILABLE", 22.0)
    assert rows[4] == ("CR-005", "DEL", "FIRST_OFFICER", "A320", "ON_LEAVE", 0.0)
    assert rows[8] == ("CR-009", "BOM", "CABIN_CREW", "ANY", "AVAILABLE", 12.0)


async def test_seed_does_not_duplicate_crew(db_session):
    await run_seed(db_session)
    await run_seed(db_session)

    assert (await db_session.execute(select(func.count()).select_from(CrewMember))).scalar_one() == 9


async def test_seed_creates_cargo_demand_for_every_route(db_session):
    await run_seed(db_session)
    origin, destination = Airport.__table__.alias("o"), Airport.__table__.alias("d")

    rows = (
        await db_session.execute(
            select(origin.c.code, destination.c.code, CargoDemand.period, CargoDemand.weekly_demand_kg,
                   CargoDemand.capacity_kg_per_flight, CargoDemand.rate_usd_per_kg,
                   CargoDemand.handling_cost_usd_per_kg)
            .select_from(CargoDemand)
            .join(Route, Route.id == CargoDemand.route_id)
            .join(origin, origin.c.id == Route.origin_id)
            .join(destination, destination.c.id == Route.destination_id)
            .order_by(CargoDemand.weekly_demand_kg.desc())
        )
    ).all()

    assert rows == [
        ("BOM", "DEL", "2026-Q3", 16000.0, 2000.0, 1.2, 0.3),
        ("DEL", "BOM", "2026-Q3", 9000.0, 2000.0, 1.2, 0.3),
        ("BOM", "BLR", "2026-Q3", 8000.0, 1800.0, 1.0, 0.2),
        ("MAA", "CCU", "2026-Q3", 2600.0, 1800.0, 1.1, 0.28),
        ("BLR", "HYD", "2026-Q3", 2000.0, 1500.0, 0.8, 0.2),
    ]


async def test_seed_does_not_duplicate_cargo_demand(db_session):
    await run_seed(db_session)
    await run_seed(db_session)

    assert (await db_session.execute(select(func.count()).select_from(CargoDemand))).scalar_one() == 5
