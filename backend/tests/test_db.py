import uuid

from app.models.base import TimestampedBase
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String


class _Widget(TimestampedBase):
    __tablename__ = "test_widgets"
    name: Mapped[str] = mapped_column(String, default="widget")


async def test_timestamped_base_assigns_id_and_created_at(db_session):
    widget = _Widget()
    db_session.add(widget)
    await db_session.flush()

    assert isinstance(widget.id, uuid.UUID)
    assert widget.created_at is not None
