import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DATABASE_URL

ADMIN_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
PREVIOUS_REVISION = "c4d8e2f1a9b3"


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


async def _seed_airports(engine, codes):
    async with engine.begin() as conn:
        for code in codes:
            await conn.execute(text(
                "INSERT INTO airports (id, code, name, city, country, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :code, 'x', 'x', 'x', now(), now())"
            ), {"code": code})


async def _crew(engine):
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT c.employee_code, a.code, c.role, c.status, c.weekly_duty_hours, c.max_weekly_duty_hours "
            "FROM crew_members c JOIN airports a ON a.id = c.base_id ORDER BY c.employee_code"
        ))).all()


async def test_upgrade_backfills_crew_for_an_already_seeded_database(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", PREVIOUS_REVISION)
    await _seed_airports(engine, ["BOM", "DEL"])

    _alembic(url, "upgrade", "head")

    rows = await _crew(engine)
    assert [r[0] for r in rows] == ["CR-001", "CR-002", "CR-003", "CR-004", "CR-005", "CR-009"]  # BOM and DEL only
    assert rows[0] == ("CR-001", "BOM", "CAPTAIN", "AVAILABLE", 22.0, 40.0)
    assert rows[4] == ("CR-005", "DEL", "FIRST_OFFICER", "ON_LEAVE", 0.0, 40.0)


async def test_upgrade_on_an_empty_database_inserts_no_crew(scratch_db):
    url, engine = scratch_db

    _alembic(url, "upgrade", "head")

    assert await _crew(engine) == []


async def test_downgrade_drops_the_crew_table_and_upgrade_recreates_it(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", "head")

    _alembic(url, "downgrade", PREVIOUS_REVISION)
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('crew_members')"))).scalar() is None

    _alembic(url, "upgrade", "head")
    assert await _crew(engine) == []
