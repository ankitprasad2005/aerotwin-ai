import uuid
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Base, get_db  # get_db re-exported: the single implementation lives in app.db
from app.events.bus import EventBus, event_bus
from app.llm.base import LLMProvider
from app.llm.openai_provider import OpenAIProvider

__all__ = ["get_db", "get_bus", "get_llm_provider", "get_or_404"]

ModelT = TypeVar("ModelT", bound=Base)


def get_bus() -> EventBus:
    return event_bus


def get_llm_provider() -> LLMProvider:
    return OpenAIProvider()


async def get_or_404(db: AsyncSession, model: type[ModelT], obj_id: uuid.UUID, detail: str) -> ModelT:
    obj = await db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=detail)
    return obj
