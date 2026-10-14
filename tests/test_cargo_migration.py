import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DATABASE_URL

ADMIN_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
PREVIOUS_REVISION = "d7a1b3c5e9f2"


def _alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "AEROTWIN_DATABASE_URL": database_url}
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, env=env, capture_output=True)


@pytest.fixture
async def scratch_db():
    name = f"aerotwin_migration_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = TEST_DATABASE_URL.rsplit("/", 1)[0] + f"/{name}"
    engine = create_async_engine(url)
    yield url, engine
    await engine.dispose()
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    await admin.dispose()


async def _seed_routes(engine, pairs):
    async with engine.begin() as conn:
        for code in sorted({c for pair in pairs for c in pair}):
            await conn.execute(text(
                "INSERT INTO airports (id, code, name, city, country, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :code, 'x', 'x', 'x', now(), now())"
            ), {"code": code})
        for origin, destination in pairs:
            await conn.execute(text(
                "INSERT INTO routes (id, origin_id, destination_id, distance_km, current_frequency, created_at, updated_at) "
                "SELECT gen_random_uuid(), o.id, d.id, 100, 3, now(), now() FROM airports o, airports d "
                "WHERE o.code = :o AND d.code = :d"
            ), {"o": origin, "d": destination})


async def _cargo(engine):
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT o.code, d.code, c.period, c.weekly_demand_kg, c.capacity_kg_per_flight, c.rate_usd_per_kg, "
            "c.handling_cost_usd_per_kg FROM cargo_demand c JOIN routes r ON r.id = c.route_id "
            "JOIN airports o ON o.id = r.origin_id JOIN airports d ON d.id = r.destination_id "
            "ORDER BY o.code, d.code"
        ))).all()


async def test_upgrade_backfills_cargo_for_seeded_routes_only(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", PREVIOUS_REVISION)
    await _seed_routes(engine, [("BOM", "DEL"), ("HYD", "BLR")])  # HYD-BLR is not a seeded route

    _alembic(url, "upgrade", "head")

    assert await _cargo(engine) == [("BOM", "DEL", "2026-Q3", 16000.0, 2000.0, 1.2, 0.3)]


async def test_upgrade_on_an_empty_database_inserts_no_cargo(scratch_db):
    url, engine = scratch_db

    _alembic(url, "upgrade", "head")

    assert await _cargo(engine) == []


async def test_downgrade_drops_the_cargo_table_and_upgrade_recreates_it(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", "head")

    _alembic(url, "downgrade", PREVIOUS_REVISION)
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('cargo_demand')"))).scalar() is None

    _alembic(url, "upgrade", "head")
    assert await _cargo(engine) == []
