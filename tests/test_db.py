import os
import uuid

import pytest
from app.models.base import TimestampedBase
from sqlalchemy import String, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

import app.db as db_module

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://aerotwin:aerotwin@localhost:5432/aerotwin_test",
)


class _Widget(TimestampedBase):
    __tablename__ = "test_widgets"
    name: Mapped[str] = mapped_column(String, default="widget")


async def test_timestamped_base_assigns_id_and_created_at(db_session):
    widget = _Widget()
    db_session.add(widget)
    await db_session.flush()

    assert isinstance(widget.id, uuid.UUID)
    assert widget.created_at is not None


async def test_get_db_yields_a_working_session_and_closes_cleanly(monkeypatch):
    """Exercises the real production get_db() dependency body (not the test
    fixture's own session factory): points its module-level async_session_factory
    at the test database, confirms the yielded session can run a real query, and
    that exhausting the generator runs the `async with` block's __aexit__ (session
    close) without error."""
    test_engine = create_async_engine(TEST_DATABASE_URL)
    test_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    gen = db_module.get_db()
    session = await gen.__anext__()
    result = await session.execute(text("SELECT 1"))
    assert result.scalar() == 1

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    await test_engine.dispose()
