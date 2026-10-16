import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DATABASE_URL

ADMIN_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
PREVIOUS_REVISION = "b7e2c4d6f8a0"
REVISION = "c7e2a9d4b6f8"
TABLES = ("airworthiness_directives", "weather_tafs")


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


async def _existing(engine) -> list[str]:
    async with engine.connect() as conn:
        return [t for t in TABLES if (await conn.execute(text("SELECT to_regclass(:t)"), {"t": t})).scalar() is not None]


async def test_upgrade_creates_the_airworthiness_directive_and_taf_tables(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", PREVIOUS_REVISION)
    assert await _existing(engine) == []

    _alembic(url, "upgrade", REVISION)

    assert await _existing(engine) == list(TABLES)
    async with engine.connect() as conn:
        unique = (await conn.execute(text(
            "SELECT count(*) FROM pg_indexes WHERE tablename='airworthiness_directives' AND indexdef LIKE '%UNIQUE%(document_number)%'"
        ))).scalar()
    assert unique == 1


async def test_downgrade_drops_the_tables_and_upgrade_recreates_them(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", REVISION)

    _alembic(url, "downgrade", PREVIOUS_REVISION)
    assert await _existing(engine) == []

    _alembic(url, "upgrade", REVISION)
    assert await _existing(engine) == list(TABLES)
