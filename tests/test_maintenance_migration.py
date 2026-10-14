import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DATABASE_URL

ADMIN_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
PREVIOUS_REVISION = "7a3c5d9f1e40"


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


async def _seed_aircraft(engine, tails_and_hours):
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO airports (id, code, name, city, country, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'BOM', 'x', 'x', 'x', now(), now())"
        ))
        for tail, hours in tails_and_hours:
            await conn.execute(text(
                "INSERT INTO aircraft (id, tail_number, aircraft_type, location_id, status, fuel_level_pct, "
                "flight_hours, maintenance_status, created_at, updated_at) "
                "SELECT gen_random_uuid(), :tail, 'A320', id, 'AVAILABLE', 50, :hours, 'NORMAL', now(), now() "
                "FROM airports WHERE code = 'BOM'"
            ), {"tail": tail, "hours": hours})


async def _records(engine):
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT a.tail_number, m.check_type, m.status, m.due_at_flight_hours, m.open_defects "
            "FROM maintenance_records m JOIN aircraft a ON a.id = m.aircraft_id "
            "ORDER BY a.tail_number, m.due_at_flight_hours"
        ))).all()


async def test_upgrade_backfills_records_for_an_already_seeded_database(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", PREVIOUS_REVISION)
    await _seed_aircraft(engine, [("VT-AER1", 4281.0), ("VT-AER3", 9100.0), ("VT-OTHER", 10.0)])

    _alembic(url, "upgrade", "head")

    assert await _records(engine) == [
        ("VT-AER1", "A_CHECK", "SCHEDULED", 4350.0, 0),
        ("VT-AER3", "C_CHECK", "IN_PROGRESS", 9050.0, 2),
    ]  # unknown tail numbers get nothing; missing seeded aircraft are skipped


async def test_upgrade_on_an_empty_database_inserts_nothing(scratch_db):
    url, engine = scratch_db

    _alembic(url, "upgrade", "head")

    assert await _records(engine) == []


async def test_downgrade_drops_the_table_and_upgrade_recreates_it(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", "head")

    _alembic(url, "downgrade", PREVIOUS_REVISION)
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('maintenance_records')"))).scalar() is None

    _alembic(url, "upgrade", "head")
    assert await _records(engine) == []
