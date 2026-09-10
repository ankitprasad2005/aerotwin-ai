from app.seed.seed import run_seed
from app.tools.digital_twin_tools import query_fleet_status, query_route_profitability


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
