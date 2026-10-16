import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DATABASE_URL

ADMIN_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
REVISION = "d3f9a2c1b7e4"
BEFORE = f"{REVISION}-1"  # the revision this one revises, wherever the chain places it


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


async def _table_exists(engine) -> bool:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT to_regclass('airport_charges')"))).scalar() is not None


async def _columns(engine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'airport_charges'"))
        return {r[0] for r in rows}


async def test_upgrade_creates_the_airport_charges_table(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", BEFORE)
    assert not await _table_exists(engine)

    _alembic(url, "upgrade", REVISION)

    assert await _table_exists(engine)
    assert await _columns(engine) >= {
        "airport", "charge_type", "basis", "slab_from_tonnes", "slab_to_tonnes", "rate_inr", "currency", "applies_to",
        "effective_from", "effective_to", "source_url", "source_title", "page",
    }


async def test_downgrade_drops_the_table_and_upgrade_recreates_it(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", REVISION)

    _alembic(url, "downgrade", BEFORE)
    assert not await _table_exists(engine)

    _alembic(url, "upgrade", REVISION)
    assert await _table_exists(engine)


async def test_the_migration_matches_the_model(scratch_db):
    """The columns of the migrated table equal the ORM model's, so create_all and alembic agree."""
    from app.models.external import AirportCharge

    url, engine = scratch_db
    _alembic(url, "upgrade", REVISION)
    assert await _columns(engine) == {c.name for c in AirportCharge.__table__.columns}
