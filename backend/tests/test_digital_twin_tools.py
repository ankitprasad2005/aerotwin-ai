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
