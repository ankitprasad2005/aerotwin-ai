from sqlalchemy import select, func

from app.models.digital_twin import Airport, Aircraft, Route, Flight, PassengerDemand
from app.seed.seed import run_seed


async def test_seed_creates_expected_counts(db_session):
    await run_seed(db_session)

    airport_count = (await db_session.execute(select(func.count()).select_from(Airport))).scalar_one()
    aircraft_count = (await db_session.execute(select(func.count()).select_from(Aircraft))).scalar_one()
    route_count = (await db_session.execute(select(func.count()).select_from(Route))).scalar_one()

    assert airport_count == 6
    assert aircraft_count >= 4
    assert route_count >= 5


async def test_seed_is_idempotent(db_session):
    await run_seed(db_session)
    await run_seed(db_session)

    airport_count = (await db_session.execute(select(func.count()).select_from(Airport))).scalar_one()
    assert airport_count == 6  # not doubled on second run
