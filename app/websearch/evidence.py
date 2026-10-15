"""Web search evidence provider (stub; filled in by the web search workstream)."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.evidence.base import EvidenceItem, EvidenceRequest


async def web_search(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    return []
