import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DATABASE_URL

ADMIN_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
PREVIOUS_REVISION = "e9b2c4d6f8a1"
TABLES = (
    "dataset_snapshots", "market_routes", "fuel_prices", "fx_rates", "dgca_traffic", "web_search_cache",
    "decision_weight_profiles",
)


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


def _is_app_table(obj, name, type_, reflected, compare_to) -> bool:
    return not (type_ == "table" and name.startswith("test_"))


async def _existing(engine) -> list[str]:
    async with engine.connect() as conn:
        return [t for t in TABLES if (await conn.execute(text("SELECT to_regclass(:t)"), {"t": t})).scalar() is not None]


async def test_upgrade_creates_every_external_table(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", PREVIOUS_REVISION)
    assert await _existing(engine) == []

    _alembic(url, "upgrade", "head")

    assert await _existing(engine) == list(TABLES)


async def test_downgrade_drops_the_tables_and_upgrade_recreates_them(scratch_db):
    url, engine = scratch_db
    _alembic(url, "upgrade", "head")

    _alembic(url, "downgrade", PREVIOUS_REVISION)
    assert await _existing(engine) == []

    _alembic(url, "upgrade", "head")
    assert await _existing(engine) == list(TABLES)


async def test_migrated_schema_matches_models(scratch_db):
    """The migration and the ORM models agree: alembic autogenerate finds no external-table diff."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db import Base

    url, engine = scratch_db
    _alembic(url, "upgrade", "head")
    async with engine.connect() as conn:
        diffs = await conn.run_sync(lambda sync: compare_metadata(
            # Other tests register throwaway test_* tables on the shared metadata; ignore them.
            MigrationContext.configure(sync, opts={"include_object": _is_app_table}), Base.metadata,
        ))
    assert diffs == []
