"""Read-side queries over the normalised dataset tables (shared by the API and the evidence providers)."""
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external import DatasetSnapshot, DgcaTraffic, FuelPrice, FxRate, MarketRoute


async def latest_snapshot(db: AsyncSession, source: str, *, status: str | None = None) -> DatasetSnapshot | None:
    stmt = select(DatasetSnapshot).where(DatasetSnapshot.source == source)
    if status is not None:
        stmt = stmt.where(DatasetSnapshot.status == status)
    stmt = stmt.order_by(DatasetSnapshot.fetched_at.desc(), DatasetSnapshot.created_at.desc()).limit(1)
    return (await db.execute(stmt)).scalars().first()


async def fuel_prices(db: AsyncSession, days: int, today: date | None = None) -> list[FuelPrice]:
    """Prices from the last `days` days (ascending by date)."""
    since = (today or date.today()) - timedelta(days=days)
    stmt = select(FuelPrice).where(FuelPrice.price_date >= since).order_by(FuelPrice.price_date)
    return list((await db.execute(stmt)).scalars().all())


async def fx_rates(db: AsyncSession, quote: str, days: int, today: date | None = None) -> list[FxRate]:
    since = (today or date.today()) - timedelta(days=days)
    stmt = (
        select(FxRate)
        .where(FxRate.quote == quote.upper(), FxRate.rate_date >= since)
        .order_by(FxRate.rate_date)
    )
    return list((await db.execute(stmt)).scalars().all())


async def market_routes(db: AsyncSession, origin: str | None = None, destination: str | None = None) -> list[MarketRoute]:
    stmt = select(MarketRoute)
    if origin:
        stmt = stmt.where(MarketRoute.origin == origin.upper())
    if destination:
        stmt = stmt.where(MarketRoute.destination == destination.upper())
    stmt = stmt.order_by(MarketRoute.origin, MarketRoute.destination, MarketRoute.airline_name, MarketRoute.airline_code)
    return list((await db.execute(stmt)).scalars().all())


async def dgca_traffic(db: AsyncSession) -> list[DgcaTraffic]:
    """All rows, latest period first, biggest market share first within a period."""
    stmt = select(DgcaTraffic).order_by(
        DgcaTraffic.period.desc(), DgcaTraffic.market_share_pct.desc().nulls_last(), DgcaTraffic.airline
    )
    return list((await db.execute(stmt)).scalars().all())


async def latest_dgca_period(db: AsyncSession) -> str | None:
    return (await db.execute(select(func.max(DgcaTraffic.period)))).scalar_one_or_none()
