"""Read-side queries over the normalised dataset tables (shared by the API and the evidence providers)."""
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.weather import AIRPORT_STATIONS, OPEN_METEO_SOURCE
from app.models.external import (
    SNAPSHOT_SUCCESS, AirworthinessDirective, DatasetSnapshot, DgcaTraffic, FuelPrice, FxRate, MarketRoute, OilPrice,
    WeatherForecast, WeatherObservation, WeatherTaf,
)

AD_WINDOW_DAYS = 365


async def airworthiness_directives(
    db: AsyncSession, aircraft_type: str | None = None, today: date | None = None
) -> list[AirworthinessDirective]:
    """ADs published in the last 365 days (newest first), optionally only those concerning `aircraft_type`."""
    since = (today or date.today()) - timedelta(days=AD_WINDOW_DAYS)
    stmt = select(AirworthinessDirective).where(AirworthinessDirective.publication_date >= since)
    if aircraft_type is not None:
        stmt = stmt.where(AirworthinessDirective.aircraft_types.contains([aircraft_type]))
    stmt = stmt.order_by(AirworthinessDirective.publication_date.desc(), AirworthinessDirective.document_number.desc())
    return list((await db.execute(stmt)).scalars().all())


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


async def brent_prices(db: AsyncSession, days: int, today: date | None = None) -> list[OilPrice]:
    """Brent prices from the last `days` days (ascending by date)."""
    since = (today or date.today()) - timedelta(days=days)
    stmt = select(OilPrice).where(OilPrice.price_date >= since).order_by(OilPrice.price_date)
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


async def weather_by_airport(db: AsyncSession) -> dict[str, dict]:
    """For each twin airport (twin order): its latest observation (or None), its latest TAF (or None) and the
    forecast days of the latest successful Open-Meteo snapshot (ascending by date; empty when there is no such snapshot)."""
    return await weather_for_airports(db, list(AIRPORT_STATIONS))


async def weather_for_airports(db: AsyncSession, airports: list[str]) -> dict[str, dict]:
    """`weather_by_airport` for any list of (IATA) airport codes, in that order."""
    newest = (
        select(WeatherObservation.airport, func.max(WeatherObservation.observed_at).label("observed_at"))
        .where(WeatherObservation.airport.in_(airports))
        .group_by(WeatherObservation.airport)
        .subquery()
    )
    observed = (
        await db.execute(
            select(WeatherObservation).join(
                newest,
                (WeatherObservation.airport == newest.c.airport) & (WeatherObservation.observed_at == newest.c.observed_at),
            )
        )
    ).scalars().all()
    observation_by_airport = {o.airport: o for o in observed}
    tafs = (
        await db.execute(
            select(WeatherTaf).where(WeatherTaf.airport.in_(airports)).order_by(WeatherTaf.airport, WeatherTaf.issued_at)
        )
    ).scalars().all()
    taf_by_airport = {t.airport: t for t in tafs}  # ascending, so the newest issue of an airport wins
    forecasts: dict[str, list[WeatherForecast]] = {}
    snapshot = await latest_snapshot(db, OPEN_METEO_SOURCE, status=SNAPSHOT_SUCCESS)
    if snapshot is not None:
        rows = (
            await db.execute(
                select(WeatherForecast)
                .where(WeatherForecast.snapshot_id == snapshot.id, WeatherForecast.airport.in_(airports))
                .order_by(WeatherForecast.airport, WeatherForecast.forecast_date)
            )
        ).scalars().all()
        for row in rows:
            forecasts.setdefault(row.airport, []).append(row)
    return {
        airport: {
            "observation": observation_by_airport.get(airport),
            "taf": taf_by_airport.get(airport),
            "forecast": forecasts.get(airport, []),
        }
        for airport in airports
    }
