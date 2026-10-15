"""Evidence providers backed by the downloaded datasets (stubs; filled in by the datasets workstream)."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.evidence.base import EvidenceItem, EvidenceRequest


async def market_competition(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    return []


async def fuel_price(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    return []


async def fx_rate(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    return []


async def dgca_market(db: AsyncSession, request: EvidenceRequest) -> list[EvidenceItem]:
    return []
