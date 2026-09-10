from app.db import get_db  # re-exported: the single get_db implementation lives in app.db
from app.events.bus import EventBus, event_bus
from app.llm.base import LLMProvider
from app.llm.openai_provider import OpenAIProvider

__all__ = ["get_db", "get_bus", "get_llm_provider"]


def get_bus() -> EventBus:
    return event_bus


def get_llm_provider() -> LLMProvider:
    return OpenAIProvider()
